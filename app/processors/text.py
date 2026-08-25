"""TXT-1, TXT-2: 텍스트 문서 OCR 처리기.

전처리(`app.preprocess`)를 거친 이미지 한 장을 받아
1) pytesseract로 한국어/영어 혼용 텍스트를 인식하고 (TXT-1),
2) img2pdf로 이미지를 한 장짜리 PDF로 감싼 뒤 OCRmyPDF로 투명 텍스트
   레이어를 입혀 검색·복사 가능한 PDF를 생성한다 (TXT-2).

인식된 텍스트 문자열은 `TextOcrResult.text`로 그대로 노출되므로, Phase1-6의
검수 UI(TXT-3)가 이 값을 보여주고 사용자가 수정할 수 있게 된다(이 모듈 자체는
검수 UI를 다루지 않는다). 이때 `TextOcrResult.text`는 OCRmyPDF가 PDF에 실제로
삽입한 텍스트 레이어(sidecar 출력)와 동일한 소스에서 나오므로, 검수 화면에서
보는 텍스트와 최종 PDF의 검색/복사 결과가 항상 일치한다.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import img2pdf
import numpy as np
import ocrmypdf
import pytesseract

from app.preprocess.pipeline import PreprocessConfig, run_pipeline

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "kor+eng"
DEFAULT_DPI = 300


class MissingExternalToolError(RuntimeError):
    """OCR/PDF 생성에 필요한 외부 프로그램(Tesseract/Ghostscript/qpdf 등)이 없거나
    설정(언어팩 등)이 잘못됐을 때 발생시킨다. 조용히 삼키지 않고 원인을 드러낸다."""


@dataclass
class TextOcrResult:
    """텍스트 처리기가 페이지 한 장을 처리한 결과."""

    text: str
    """OCR로 인식된 문자열 (TXT-1)."""

    pdf_path: Path
    """투명 텍스트 레이어가 삽입된 검색 가능 PDF 경로 (TXT-2)."""


def _require_tesseract() -> None:
    if shutil.which("tesseract") is None:
        raise MissingExternalToolError(
            "tesseract 실행 파일을 찾을 수 없습니다. `brew install tesseract`로 설치한 뒤 "
            "PATH에 등록되어 있는지 확인하세요."
        )


def extract_text(image: np.ndarray, *, lang: str = DEFAULT_LANGUAGE) -> str:
    """TXT-1: 전처리된 이미지에서 한국어/영어 혼용 텍스트를 인식한다.

    `process_image()`/`build_searchable_pdf()` 경로는 OCRmyPDF의 sidecar 출력을
    최종 텍스트로 쓰므로 이 함수를 내부적으로 다시 호출하지 않는다. 텍스트만
    단독으로 필요한 호출자(예: 빠른 미리보기)를 위해 별도 진입점으로 유지한다.
    """
    _require_tesseract()
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    try:
        return pytesseract.image_to_string(grayscale, lang=lang)
    except pytesseract.TesseractNotFoundError as exc:
        raise MissingExternalToolError(
            "tesseract 실행 파일을 찾을 수 없습니다. `brew install tesseract`로 설치하세요."
        ) from exc
    except pytesseract.TesseractError as exc:
        raise MissingExternalToolError(
            f"Tesseract OCR 실행에 실패했습니다(언어팩 '{lang}' 누락 가능성 있음, "
            f"`tesseract --list-langs`로 설치된 언어를 확인하세요): {exc}"
        ) from exc


def _image_to_pdf_bytes(image: np.ndarray, *, dpi: int) -> bytes:
    """이미지를 한 장짜리 PDF 바이트로 감싼다 (OCRmyPDF의 입력은 PDF여야 하므로).

    `img2pdf.get_fixed_dpi_layout_fun`으로 DPI를 명시해야 PDF 페이지 크기가 실제
    인쇄 크기 기준으로 맞춰지고, OCRmyPDF/Tesseract가 해상도를 오인하지 않는다.
    """
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("이미지를 PNG로 인코딩하는 데 실패했습니다.")
    layout_fun = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
    return img2pdf.convert(encoded.tobytes(), layout_fun=layout_fun)


def _build_searchable_pdf_with_sidecar_text(
    image: np.ndarray,
    output_pdf: str | Path,
    *,
    lang: str,
    dpi: int,
) -> tuple[Path, str]:
    """OCRmyPDF를 한 번만 실행해 PDF와 그 안에 실제로 임베딩된 텍스트를 함께 얻는다.

    `extract_text()`(순수 pytesseract 호출)와 별도로 Tesseract를 다시 돌리면,
    두 호출의 내부 파라미터/순서가 미묘하게 달라 인식 결과가 어긋날 수 있다
    (검수 UI에 보이는 텍스트가 실제 PDF 텍스트 레이어와 달라지는 문제).
    `sidecar=` 옵션으로 OCRmyPDF가 실제로 사용한 텍스트를 그대로 뽑아내
    이 어긋남을 원천 차단한다.
    """
    _require_tesseract()
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    pdf_bytes = _image_to_pdf_bytes(image, dpi=dpi)
    with tempfile.TemporaryDirectory() as tmp_dir:
        intermediate_pdf = Path(tmp_dir) / "wrapped.pdf"
        intermediate_pdf.write_bytes(pdf_bytes)
        sidecar_path = Path(tmp_dir) / "sidecar.txt"
        try:
            ocrmypdf.ocr(intermediate_pdf, output_pdf, language=lang, sidecar=sidecar_path)
        except ocrmypdf.MissingDependencyError as exc:
            raise MissingExternalToolError(
                "OCRmyPDF 실행에 필요한 외부 프로그램(Ghostscript/qpdf 등)을 찾을 수 "
                f"없습니다. `brew install ghostscript qpdf`로 설치하세요: {exc}"
            ) from exc

        if sidecar_path.exists():
            sidecar_text = sidecar_path.read_text(encoding="utf-8")
        else:
            # OCRmyPDF가 내부적으로 페이지를 건너뛰는 등(예: Ghostscript가 페이지를
            # 래스터화하지 못해 degrade하는 경우) sidecar가 생성되지 않을 수 있다.
            # 조용히 빈 문자열을 반환하는 대신 원인을 남기고, 검수 UI가 최소한의
            # 텍스트라도 볼 수 있도록 별도 pytesseract 호출로 대체한다.
            logger.warning(
                "OCRmyPDF가 sidecar 텍스트 파일을 생성하지 않았습니다(%s). "
                "extract_text()로 대체 인식을 시도합니다.",
                sidecar_path,
            )
            sidecar_text = extract_text(image, lang=lang)

    return output_pdf, sidecar_text


def build_searchable_pdf(
    image: np.ndarray,
    output_pdf: str | Path,
    *,
    lang: str = DEFAULT_LANGUAGE,
    dpi: int = DEFAULT_DPI,
) -> Path:
    """TXT-2: 이미지를 PDF로 감싼 뒤 OCRmyPDF로 투명 텍스트 레이어를 입힌다."""
    pdf_path, _ = _build_searchable_pdf_with_sidecar_text(image, output_pdf, lang=lang, dpi=dpi)
    return pdf_path


def process_image(
    image: np.ndarray,
    output_pdf: str | Path,
    *,
    lang: str = DEFAULT_LANGUAGE,
    dpi: int = DEFAULT_DPI,
) -> TextOcrResult:
    """진입점: 전처리 완료된 이미지 한 장 → (인식 텍스트, 검색 가능 PDF).

    Phase1-4(PDF 조립)가 여러 페이지를 순회하며 호출하기 편하도록 페이지 한 장
    단위로 동작하고, 검수(TXT-3)에 쓰일 텍스트와 다음 단계에서 병합할 PDF 경로를
    함께 반환한다. 이미지가 이미 `app.preprocess.run_pipeline`을 거쳤다고 가정한다
    (GUI는 보통 미리보기를 위해 전처리를 먼저 실행해두므로 이중 처리를 피한다).

    반환되는 `TextOcrResult.text`는 PDF에 실제로 삽입된 텍스트 레이어와 동일한
    소스(OCRmyPDF의 sidecar 출력)에서 나온다 — Tesseract를 두 번 따로 호출하면
    두 결과가 미묘하게 달라질 수 있어, 검수 UI가 보여주는 텍스트와 실제 PDF
    검색/복사 결과가 어긋나지 않도록 한 번의 호출로 통일한다.
    """
    pdf_path, text = _build_searchable_pdf_with_sidecar_text(image, output_pdf, lang=lang, dpi=dpi)
    return TextOcrResult(text=text, pdf_path=pdf_path)


def process_image_file(
    input_path: str | Path,
    output_pdf: str | Path,
    *,
    lang: str = DEFAULT_LANGUAGE,
    dpi: int = DEFAULT_DPI,
    preprocess_config: PreprocessConfig | None = None,
) -> TextOcrResult:
    """편의 진입점: 원본 이미지 파일 경로를 받아 공통 전처리부터 한 번에 수행한다.

    GUI처럼 페이지별 전처리 미리보기를 이미 거친 뒤 호출하는 경로는
    `process_image()`를 직접 쓰면 되고, 미리보기 없이 파일 → PDF를 한 번에
    처리하고 싶은 배치성 호출자는 이 함수를 쓰면 된다.
    """
    input_path = Path(input_path)
    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {input_path}")
    preprocessed = run_pipeline(image, preprocess_config)
    return process_image(preprocessed, output_pdf, lang=lang, dpi=dpi)
