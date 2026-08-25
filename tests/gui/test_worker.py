"""Phase1-5(GUI-1,2,4) 수용 기준 검증: `ProcessingWorker`가 별도 QThread에서 실행되는지.

CLAUDE.md에 명시된 대로 pytest-qt 공식 예제(`qtbot.waitSignal(worker.finished, ...)`,
https://pytest-qt.readthedocs.io/en/latest/signals.html) 패턴으로 비동기 완료를
검증한다. Tesseract/Ghostscript/qpdf가 이 머신에 설치돼 있어야 실제 파이프라인이
끝까지 도는데, `tests/processors/test_text.py`와 동일하게 없으면 skip한다.
"""

from __future__ import annotations

import shutil

import cv2
import pymupdf
import pytest

from app.gui.worker import ProcessingWorker

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None

pytestmark = pytest.mark.skipif(
    not (_TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE),
    reason="tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다.",
)


def test_processing_worker_runs_in_background_thread_and_produces_merged_pdf(
    qtbot, tmp_path, synthetic_text_photo
):
    """워커를 시작한 뒤 QThread의 내장 `finished` 시그널로 완료를 기다릴 수 있어야 한다."""
    image_path = tmp_path / "page1.png"
    cv2.imwrite(str(image_path), synthetic_text_photo.photo)
    work_dir = tmp_path / "work"

    worker = ProcessingWorker([image_path], work_dir)

    with qtbot.waitSignal(worker.finished, timeout=120000):
        worker.start()

    assert worker.isRunning() is False
    assert worker.merged_pdf_path is not None
    assert worker.merged_pdf_path.exists()
    assert len(worker.page_results) == 1
    assert worker.page_results[0].text.strip() != ""

    with pymupdf.open(worker.merged_pdf_path) as doc:
        assert doc.page_count == 1


def test_processing_worker_handles_multiple_pages_in_order(qtbot, tmp_path, synthetic_text_photo):
    """여러 장을 넣으면 병합 PDF 페이지 수가 그만큼 늘어나야 한다 (PDF-1 재사용 확인)."""
    image_path_1 = tmp_path / "page1.png"
    image_path_2 = tmp_path / "page2.png"
    cv2.imwrite(str(image_path_1), synthetic_text_photo.photo)
    cv2.imwrite(str(image_path_2), synthetic_text_photo.photo)
    work_dir = tmp_path / "work"

    worker = ProcessingWorker([image_path_1, image_path_2], work_dir)

    with qtbot.waitSignal(worker.finished, timeout=180000):
        worker.start()

    assert worker.merged_pdf_path is not None
    with pymupdf.open(worker.merged_pdf_path) as doc:
        assert doc.page_count == 2


def test_processing_worker_reports_error_for_unreadable_image(qtbot, tmp_path):
    """에러(이미지 로드 실패)를 조용히 삼키지 않고 `error_occurred`로 알려야 한다."""
    bogus_path = tmp_path / "not_an_image.png"
    bogus_path.write_bytes(b"not a real image")
    work_dir = tmp_path / "work"

    worker = ProcessingWorker([bogus_path], work_dir)

    with qtbot.waitSignal(worker.error_occurred, timeout=30000):
        worker.start()
    worker.wait(30000)

    assert worker.merged_pdf_path is None
