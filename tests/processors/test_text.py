"""TXT-1,2 수용 기준 검증: OCR 텍스트 인식 + 검색 가능한 PDF 생성.

Tesseract/Ghostscript/qpdf가 이 머신에 실제로 설치돼 있는 상태를 전제로 하되,
설치되지 않은 환경(예: 다른 CI 머신)에서 무너지지 않도록 `shutil.which()`로
확인해 없으면 skip한다.
"""

from __future__ import annotations

import difflib
import shutil

import pymupdf
import pytest

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.text import (
    MissingExternalToolError,
    build_searchable_pdf,
    extract_text,
    process_image,
)
from tests.fixtures.synthetic import (
    KoreanFontUnavailableError,
    make_korean_text_photo,
    make_text_photo,
)

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None

pytestmark = pytest.mark.skipif(
    not (_TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE),
    reason="tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다.",
)


def _similarity(candidate: str, expected: str) -> float:
    return difflib.SequenceMatcher(None, candidate, expected).ratio()


def _similarity_ignoring_whitespace(candidate: str, expected: str) -> float:
    """공백/줄바꿈 차이를 무시하고 문자 내용만 비교한다.

    pymupdf가 PDF의 (특히 한글처럼 글리프가 없어 보이지 않는 텍스트로 삽입된)
    텍스트 레이어를 다시 추출할 때, sidecar 원문과 글자 내용은 같아도 줄바꿈/공백
    위치를 다르게 재구성하는 경우가 있다 — 이는 sidecar와 PDF가 "다른 텍스트"를
    담고 있다는 뜻이 아니라 pymupdf의 줄 추출 휴리스틱 차이일 뿐이므로, 두
    문자열이 실제로 같은 내용인지 검증할 때는 공백을 제거하고 비교한다.
    """
    return _similarity("".join(candidate.split()), "".join(expected.split()))


@pytest.fixture
def preprocessed_text_photo():
    """합성 촬영본을 공통 전처리(run_pipeline)까지 거친 이미지와 원문을 함께 반환한다."""
    photo = make_text_photo()
    config = PreprocessConfig(corners=photo.corners, upscale_scale=3.0)
    processed = run_pipeline(photo.photo, config)
    return processed, photo.text


@pytest.fixture
def preprocessed_korean_text_photo():
    """한글+영문 혼용 합성 촬영본을 공통 전처리까지 거친 이미지와 원문을 함께 반환한다.

    시스템에 한글 지원 폰트가 없는 머신에서는 안전하게 skip한다.
    """
    try:
        photo = make_korean_text_photo()
    except KoreanFontUnavailableError as exc:
        pytest.skip(str(exc))
    config = PreprocessConfig(corners=photo.corners, upscale_scale=3.0)
    processed = run_pipeline(photo.photo, config)
    return processed, photo.text


def test_extract_text_recognizes_korean_and_english_mixed_content(preprocessed_text_photo):
    """TXT-1: 영문+숫자 혼용 텍스트 인식 결과가 원문과 충분히 유사해야 한다."""
    processed, expected_text = preprocessed_text_photo

    recognized = extract_text(processed, lang="kor+eng")

    assert _similarity(recognized, expected_text) > 0.9


def test_extract_text_recognizes_korean_content(preprocessed_korean_text_photo):
    """TXT-1: 실제 한글 글리프가 포함된 문서의 인식 결과가 원문과 충분히 유사해야 한다.

    한글 인식은 영문보다 정확도가 낮게 나올 수 있어(자소 인식 오류 등) 영문
    테스트보다는 느슨한 임계값을 쓴다.
    """
    processed, expected_text = preprocessed_korean_text_photo

    recognized = extract_text(processed, lang="kor+eng")

    assert _similarity(recognized, expected_text) > 0.7


def test_process_image_korean_text_matches_embedded_pdf_text(
    tmp_path, preprocessed_korean_text_photo
):
    """검수 UI에 노출되는 `result.text`가 실제 PDF 텍스트 레이어와 (거의) 일치해야 한다 (한글).

    Tesseract를 두 번 따로 호출하면 결과가 미묘하게 어긋날 수 있으므로, OCRmyPDF의
    sidecar 출력을 최종 텍스트로 재사용하는지를 이 테스트로 회귀 검증한다. pymupdf가
    PDF 텍스트 레이어를 다시 추출할 때 줄바꿈/공백을 sidecar 원문과 다르게 재구성할
    수 있어 완전 동일 문자열 비교 대신 매우 높은 유사도로 검증한다.
    """
    processed, _ = preprocessed_korean_text_photo
    output_pdf = tmp_path / "korean.pdf"

    result = process_image(processed, output_pdf, lang="kor+eng")

    with pymupdf.open(result.pdf_path) as doc:
        pdf_text = doc[0].get_text()

    assert _similarity_ignoring_whitespace(result.text, pdf_text) > 0.95


def test_build_searchable_pdf_embeds_text_layer(tmp_path, preprocessed_text_photo):
    """TXT-2: OCRmyPDF로 생성한 PDF에 원문 일부가 텍스트 레이어로 실제 포함돼야 한다."""
    processed, expected_text = preprocessed_text_photo
    output_pdf = tmp_path / "output.pdf"

    result_path = build_searchable_pdf(processed, output_pdf, lang="kor+eng")

    assert result_path == output_pdf
    assert output_pdf.exists()

    with pymupdf.open(output_pdf) as doc:
        assert doc.page_count == 1
        page_text = doc[0].get_text()

    assert page_text.strip() != ""
    # 원문 중 눈에 잘 띄는 한 단어("quick")가 PDF 텍스트 레이어에 그대로 검색돼야 한다.
    assert "quick" in page_text.lower()


def test_process_image_returns_text_and_pdf_together(tmp_path, preprocessed_text_photo):
    """진입점(process_image)이 인식 텍스트와 PDF 경로를 한 번에 반환해야 한다."""
    processed, expected_text = preprocessed_text_photo
    output_pdf = tmp_path / "page.pdf"

    result = process_image(processed, output_pdf, lang="kor+eng")

    assert result.pdf_path == output_pdf
    assert output_pdf.exists()
    assert _similarity(result.text, expected_text) > 0.9


def test_process_image_text_matches_embedded_pdf_text(tmp_path, preprocessed_text_photo):
    """검수 UI에 노출되는 `result.text`가 실제 PDF 텍스트 레이어와 (거의) 일치해야 한다.

    OCRmyPDF 호출을 텍스트 추출과 PDF 생성 두 번으로 나누면 Tesseract 인식
    결과가 미묘하게 달라질 수 있다 — sidecar 출력을 재사용해 이를 방지한다.
    """
    processed, _ = preprocessed_text_photo
    output_pdf = tmp_path / "consistency.pdf"

    result = process_image(processed, output_pdf, lang="kor+eng")

    with pymupdf.open(result.pdf_path) as doc:
        pdf_text = doc[0].get_text()

    assert _similarity_ignoring_whitespace(result.text, pdf_text) > 0.95


def test_extract_text_raises_clear_error_for_unknown_language(preprocessed_text_photo):
    """존재하지 않는 언어팩을 지정하면 원인을 알 수 있는 예외를 던져야 한다(조용히 삼키지 않음)."""
    processed, _ = preprocessed_text_photo

    with pytest.raises(MissingExternalToolError):
        extract_text(processed, lang="not_a_real_language_pack")
