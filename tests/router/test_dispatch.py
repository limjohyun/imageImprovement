"""RT-2 수용 기준 검증: 분류 결과에 따른 처리기 위임.

텍스트 유형은 실제 `app.processors.text.process_image`로, 도형 유형은
`app.processors.diagram.process_image`로, 악보 유형은 `app.processors.score.process_image`로
위임되는지 확인한다(텍스트는 Tesseract/Ghostscript/qpdf가 없으면 skip).

이 개발 머신엔 oemer OMR 체크포인트가 없으므로(Phase3-1에서 의도적으로 다운로드
보류, 수백MB), 악보 위임 테스트는 실제 인식 성공 대신 `route_and_process`가
`ScoreModelUnavailableError`로 이어지는지만 확인한다 — 이는 라우팅 자체가
`score.process_image`까지 정확히 위임됐다는 증거이기도 하다(위임되지 않았다면
`UnsupportedDocumentTypeError`가 먼저 났을 것이다).
"""

from __future__ import annotations

import shutil

import pytest

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.diagram import DiagramResult
from app.processors.score import ScoreModelUnavailableError
from app.processors.text import TextOcrResult
from app.router.classifier import DocumentType
from app.router.dispatch import route_and_process
from tests.fixtures.synthetic import SyntheticPhoto

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None
_TEXT_PIPELINE_AVAILABLE = _TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE


@pytest.mark.skipif(
    not _TEXT_PIPELINE_AVAILABLE, reason="tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다."
)
def test_route_and_process_delegates_text_to_text_processor(
    synthetic_text_photo: SyntheticPhoto, tmp_path
) -> None:
    preprocessed = run_pipeline(synthetic_text_photo.photo, PreprocessConfig())
    output_pdf = tmp_path / "output.pdf"

    result = route_and_process(
        preprocessed, output_pdf, override=DocumentType.TEXT
    )

    assert isinstance(result, TextOcrResult)
    assert output_pdf.exists()


def test_route_and_process_delegates_diagram_to_diagram_processor(
    synthetic_diagram_photo: SyntheticPhoto, tmp_path
) -> None:
    preprocessed = run_pipeline(synthetic_diagram_photo.photo, PreprocessConfig())
    output_pdf = tmp_path / "output.pdf"

    result = route_and_process(preprocessed, output_pdf, override=DocumentType.DIAGRAM)

    assert isinstance(result, DiagramResult)
    assert output_pdf.exists()
    assert result.svg_path is None  # 벡터화는 명시적으로 요청하지 않는 한 실행되지 않는다.


def test_route_and_process_delegates_score_to_score_processor(
    synthetic_score_photo: SyntheticPhoto, tmp_path
) -> None:
    """SCORE로 분류되면 `app.processors.score.process_image`로 위임되어야 한다.

    체크포인트 미설치 환경에서는 `ScoreModelUnavailableError`가 나는 것이 정상이며,
    이 예외가 (조용히 무시되거나 텍스트/도형 처리기로 폴백되는 대신) 명확하게
    전파되는지가 이 테스트의 핵심이다.
    """
    preprocessed = run_pipeline(synthetic_score_photo.photo, PreprocessConfig())
    output_pdf = tmp_path / "output.pdf"

    with pytest.raises(ScoreModelUnavailableError):
        route_and_process(preprocessed, output_pdf, override=DocumentType.SCORE)
