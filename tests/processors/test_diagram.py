"""DIA-1 수용 기준 검증: 저해상도 도형 이미지를 확대해도 윤곽이 뭉개지지 않아야 한다.

라플라시안 분산(선명도의 대리 지표로 널리 쓰이는 값 — 값이 클수록 경계가
또렷함)이 선명화 전후로 개선되는지, 그리고 결과 PDF가 유효한 한 장짜리 PDF인지를
최소한으로 검증한다. 본격적인 회귀 테스트 보강은 qa-test-engineer가 이어서 담당한다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import cv2
import pymupdf

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.diagram import (
    VECTORIZATION_DISCLAIMER,
    DiagramResult,
    build_diagram_pdf,
    process_image,
    sharpen_diagram,
    vectorize_diagram,
)
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


def test_process_image_does_not_vectorize_by_default(tmp_path):
    """DIA-2: "사용자가 요청 시"만 벡터화해야 하므로, 기본값은 벡터화를 실행하지 않아야 한다."""
    processed = _preprocessed_diagram_photo()
    output_pdf = tmp_path / "page.pdf"

    result = process_image(processed, output_pdf)

    assert result.svg_path is None
    assert result.vectorization_disclaimer is None
    # output_pdf와 같은 이름의 .svg가 요청하지 않았는데 생겨서는 안 된다.
    assert not output_pdf.with_suffix(".svg").exists()


def test_vectorize_diagram_creates_valid_svg(tmp_path):
    """DIA-2: 벡터화 결과가 실제로 파싱 가능한 최소 구조의 SVG 파일이어야 한다."""
    processed = _preprocessed_diagram_photo()
    sharpened = sharpen_diagram(processed)
    output_svg = tmp_path / "diagram.svg"

    result_path = vectorize_diagram(sharpened, output_svg)

    assert result_path == output_svg
    assert output_svg.exists()

    root = ET.fromstring(output_svg.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    assert root.attrib.get("width")
    assert root.attrib.get("height")


def test_process_image_with_vectorize_true_returns_svg_and_disclaimer(tmp_path):
    """DIA-2/DIA-3: 벡터화를 요청하면 SVG 경로와 한계 고지 문구가 함께 채워져야 한다."""
    processed = _preprocessed_diagram_photo()
    output_pdf = tmp_path / "page.pdf"

    result = process_image(processed, output_pdf, vectorize=True)

    assert result.svg_path is not None
    assert result.svg_path.exists()
    assert result.vectorization_disclaimer == VECTORIZATION_DISCLAIMER
    # PPTX 수준의 완전 재편집이 아니라는 취지가 실제로 문구에 담겨 있어야 한다.
    disclaimer = result.vectorization_disclaimer
    assert "PPTX" in disclaimer or "PowerPoint" in disclaimer
