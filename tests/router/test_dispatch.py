"""RT-2 수용 기준 검증: 분류 결과에 따른 처리기 위임.

텍스트 유형은 실제 `app.processors.text.process_image`로, 도형 유형은
`app.processors.diagram.process_image`로 위임되는지 확인한다(텍스트는
Tesseract/Ghostscript/qpdf가 없으면 skip). 악보 유형은 아직 처리기가 없으므로
조용히 무시되거나 다른 처리기로 폴백되지 않고 명확한 예외가 발생하는지 확인한다.
"""

from __future__ import annotations

import shutil

import pytest

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.diagram import DiagramResult
from app.processors.text import TextOcrResult
from app.router.classifier import DocumentType
from app.router.dispatch import UnsupportedDocumentTypeError, route_and_process
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


def test_route_and_process_raises_for_unimplemented_score_processor(
    synthetic_text_photo: SyntheticPhoto, tmp_path
) -> None:
    """악보 처리기가 아직 없으므로 조용히 무시하거나 다른 유형으로 폴백하면 안 된다."""
    preprocessed = run_pipeline(synthetic_text_photo.photo, PreprocessConfig())
    output_pdf = tmp_path / "output.pdf"

    with pytest.raises(UnsupportedDocumentTypeError):
        route_and_process(preprocessed, output_pdf, override=DocumentType.SCORE)
