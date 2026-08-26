"""DIA-1 수용 기준 검증: 저해상도 도형 이미지를 확대해도 윤곽이 뭉개지지 않아야 한다.

라플라시안 분산(선명도의 대리 지표로 널리 쓰이는 값 — 값이 클수록 경계가
또렷함)이 선명화 전후로 개선되는지, 그리고 결과 PDF가 유효한 한 장짜리 PDF인지를
최소한으로 검증한다. 본격적인 회귀 테스트 보강은 qa-test-engineer가 이어서 담당한다.
"""

from __future__ import annotations

import cv2
import pymupdf

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.diagram import DiagramResult, build_diagram_pdf, process_image, sharpen_diagram
from tests.fixtures.synthetic import make_diagram_photo


def _laplacian_variance(image) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _preprocessed_diagram_photo():
    photo = make_diagram_photo()
    config = PreprocessConfig(corners=photo.corners, upscale_scale=3.0)
    return run_pipeline(photo.photo, config)


def test_sharpen_diagram_improves_edge_sharpness():
    """DIA-1: 선명화 후 라플라시안 분산(경계 뚜렷함의 대리 지표)이 개선돼야 한다."""
    processed = _preprocessed_diagram_photo()

    sharpened = sharpen_diagram(processed)

    assert sharpened.shape == processed.shape
    assert sharpened.dtype == processed.dtype
    assert _laplacian_variance(sharpened) > _laplacian_variance(processed)


def test_sharpen_diagram_rejects_empty_image():
    """빈 이미지는 조용히 통과시키지 않고 명확한 예외를 던져야 한다."""
    import numpy as np
    import pytest

    with pytest.raises(ValueError):
        sharpen_diagram(np.empty((0, 0, 3), dtype=np.uint8))


def test_build_diagram_pdf_creates_single_page_pdf(tmp_path):
    """DIA-1: 선명화된 이미지가 텍스트 레이어 없이 한 장짜리 PDF로 그대로 담겨야 한다."""
    processed = _preprocessed_diagram_photo()
    sharpened = sharpen_diagram(processed)
    output_pdf = tmp_path / "diagram.pdf"

    result_path = build_diagram_pdf(sharpened, output_pdf)

    assert result_path == output_pdf
    assert output_pdf.exists()
    with pymupdf.open(output_pdf) as doc:
        assert doc.page_count == 1
        # 도형 문서는 OCR 텍스트 레이어가 없어야 한다(TXT-2는 텍스트 전용 요구사항).
        assert doc[0].get_text().strip() == ""


def test_process_image_returns_sharpened_image_and_pdf_together(tmp_path):
    """진입점(process_image)이 선명화된 이미지와 PDF 경로를 한 번에 반환해야 한다."""
    processed = _preprocessed_diagram_photo()
    output_pdf = tmp_path / "page.pdf"

    result = process_image(processed, output_pdf)

    assert isinstance(result, DiagramResult)
    assert result.pdf_path == output_pdf
    assert output_pdf.exists()
    assert _laplacian_variance(result.sharpened_image) > _laplacian_variance(processed)
