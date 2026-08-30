"""Phase4-1(GUI-3 일부) 수용 기준 검증: `MainWindow`에서 자르기/회전 보정 후 재처리.

실제 파이프라인(전처리~OCR~PDF)을 끝까지 태워 `PageResult`와 병합 PDF가 갱신되는지
확인한다. Tesseract/Ghostscript/qpdf가 이 머신에 설치돼 있어야 하므로
`tests/gui/test_worker.py`와 동일하게 없으면 skip한다.
"""

from __future__ import annotations

import shutil

import cv2
import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.gui.crop_rotate_dialog import CropRotateDialog
from app.gui.main_window import MainWindow
from app.gui.worker import PageResult
from app.router.classifier import DocumentType

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None

pytestmark = pytest.mark.skipif(
    not (_TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE),
    reason="tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다.",
)


def _add_page_with_result(window: MainWindow, result: PageResult) -> None:
    window._add_image_paths([result.input_path])
    window._results_by_input[str(result.input_path.resolve())] = result


def test_crop_rotate_button_disabled_until_page_processed(qtbot, tmp_path):
    """처리되지 않은 페이지는 자르기/회전 버튼이 비활성 상태여야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "unprocessed.png"
    image_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([image_path])
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    assert window.crop_rotate_button.isEnabled() is False


def test_crop_rotate_reprocess_updates_page_result_and_merged_pdf(
    qtbot, tmp_path, monkeypatch, synthetic_text_photo
):
    """자르기/회전을 적용해 재처리하면 `PageResult`와 병합 PDF가 실제로 갱신돼야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path / "work"
    window._work_dir.mkdir()

    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), synthetic_text_photo.photo)
    original_height, original_width = synthetic_text_photo.photo.shape[:2]

    page_pdf_path = window._work_dir / "page_001.pdf"
    initial_result = PageResult(
        input_path=image_path,
        page_pdf_path=page_pdf_path,
        text="이전 텍스트",
        document_type=DocumentType.TEXT,
    )
    _add_page_with_result(window, initial_result)
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    # 다이얼로그가 자동으로 "회전 없음 + 절반 영역만 자르기"를 선택하고 OK를 누른
    # 것처럼 동작하도록 exec()를 가로챈다(GUI 다이얼로그를 실제로 띄우지 않기 위함).
    crop_width = original_width // 2
    crop_height = original_height // 2

    def fake_exec(self):
        self.x_spin.setValue(0)
        self.y_spin.setValue(0)
        self.width_spin.setValue(crop_width)
        self.height_spin.setValue(crop_height)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CropRotateDialog, "exec", fake_exec)

    qtbot.mouseClick(window.crop_rotate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._reprocess_worker is None, timeout=120000)

    updated_result = window._results_by_input[str(image_path.resolve())]
    assert updated_result is not initial_result
    assert updated_result.crop_rect == (0, 0, crop_width, crop_height)
    assert updated_result.rotation_degrees == 0
    assert updated_result.page_pdf_path.exists()

    assert window._merged_pdf_path is not None
    with pymupdf.open(window._merged_pdf_path) as doc:
        assert doc.page_count == 1
    assert window.save_button.isEnabled() is True
