"""PDF-1 수용 기준 검증: 여러 페이지 PDF를 순서대로 하나로 병합한다."""

from __future__ import annotations

import shutil
from pathlib import Path

import pymupdf
import pytest

from app.pdf_assembly import assemble_pdf
from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.text import process_image
from tests.fixtures.synthetic import make_text_photo

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None


def _make_single_page_pdf(path: Path, label: str) -> Path:
    """텍스트 레이어가 삽입된 한 장짜리 PDF를 만든다 (외부 OCR 바이너리 없이 재현 가능)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), label)
    doc.save(path)
    doc.close()
    return path


def test_assemble_pdf_merges_pages_in_given_order(tmp_path):
    """PDF-1: 여러 장을 지정한 순서 그대로 하나의 PDF로 합쳐야 한다."""
    page_paths = [
        _make_single_page_pdf(tmp_path / "a.pdf", "PAGE-A"),
        _make_single_page_pdf(tmp_path / "b.pdf", "PAGE-B"),
        _make_single_page_pdf(tmp_path / "c.pdf", "PAGE-C"),
    ]
    output_pdf = tmp_path / "merged.pdf"

    result = assemble_pdf(page_paths, output_pdf)

    assert result == output_pdf
    assert output_pdf.exists()

    with pymupdf.open(output_pdf) as merged:
        assert merged.page_count == 3
        page_texts = [merged[i].get_text() for i in range(3)]

    assert "PAGE-A" in page_texts[0]
    assert "PAGE-B" in page_texts[1]
    assert "PAGE-C" in page_texts[2]


def test_assemble_pdf_preserves_custom_order(tmp_path):
    """호출자가 정한 순서(원본 페이지 번호와 다를 수 있음)를 그대로 보존해야 한다."""
    page_a = _make_single_page_pdf(tmp_path / "a.pdf", "FIRST")
    page_b = _make_single_page_pdf(tmp_path / "b.pdf", "SECOND")
    output_pdf = tmp_path / "reordered.pdf"

    assemble_pdf([page_b, page_a], output_pdf)

    with pymupdf.open(output_pdf) as merged:
        assert "SECOND" in merged[0].get_text()
        assert "FIRST" in merged[1].get_text()


def test_assemble_pdf_rejects_empty_input(tmp_path):
    """빈 리스트는 조용히 무시하지 않고 명확한 예외로 드러나야 한다."""
    with pytest.raises(ValueError):
        assemble_pdf([], tmp_path / "output.pdf")


def test_assemble_pdf_rejects_missing_file(tmp_path):
    """존재하지 않는 페이지 경로는 명확한 예외로 드러나야 한다."""
    existing = _make_single_page_pdf(tmp_path / "a.pdf", "PAGE-A")
    missing = tmp_path / "does_not_exist.pdf"

    with pytest.raises(FileNotFoundError):
        assemble_pdf([existing, missing], tmp_path / "output.pdf")


def test_assemble_pdf_rejects_zero_page_pdf(tmp_path):
    """페이지가 0개인 PDF가 섞여 있으면 명확한 예외로 드러나야 한다.

    pymupdf는 `save()` 자체가 0페이지 문서를 거부하므로(항상 최소 1페이지를 요구),
    페이지가 0개인 PDF 파일을 만들려면 최소한의 유효 PDF 구조를 직접 바이트로 써야 한다.
    """
    empty_pdf_path = tmp_path / "empty.pdf"
    empty_pdf_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"trailer\n<< /Size 3 /Root 1 0 R >>\n"
        b"%%EOF\n"
    )
    assert pymupdf.open(empty_pdf_path).page_count == 0

    with pytest.raises(ValueError):
        assemble_pdf([empty_pdf_path], tmp_path / "output.pdf")


@pytest.mark.skipif(
    not (_TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE),
    reason="tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다.",
)
def test_assemble_pdf_merges_real_ocr_pages(tmp_path):
    """Phase1-3 text 처리기가 만든 검색 가능 PDF들을 병합해도 순서/텍스트가 보존돼야 한다."""
    page_pdfs = []
    for i in range(2):
        photo = make_text_photo(seed=20260825 + i)
        config = PreprocessConfig(corners=photo.corners, upscale_scale=3.0)
        processed = run_pipeline(photo.photo, config)
        result = process_image(processed, tmp_path / f"page_{i}.pdf", lang="kor+eng")
        page_pdfs.append(result.pdf_path)

    output_pdf = tmp_path / "assembled.pdf"
    assemble_pdf(page_pdfs, output_pdf)

    with pymupdf.open(output_pdf) as merged:
        assert merged.page_count == len(page_pdfs)
        for i in range(len(page_pdfs)):
            assert merged[i].get_text().strip() != ""
