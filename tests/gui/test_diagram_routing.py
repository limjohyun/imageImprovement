"""Phase2-4(DIA-3 UI) 수용 기준 검증: `MainWindow`의 도형 처리 경로 UI 반응.

`ProcessingWorker`의 실제 라우팅/분류 로직은 `tests/gui/test_worker_routing.py`,
`tests/router/*`에서 이미 검증하므로, 여기서는 이미 채워진 `PageResult`를 직접
주입해 `MainWindow`가 `document_type`에 따라 화면을 올바르게 반응시키는지
(텍스트 검수 패널의 전용 안내 문구, 벡터화 버튼 활성화, DIA-3 한계 고지 노출)를
스모크 수준으로 확인한다.
"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt

from app.gui.main_window import MainWindow
from app.gui.worker import PageResult
from app.processors.diagram import VECTORIZATION_DISCLAIMER
from app.router.classifier import DocumentType


def _make_diagram_image() -> np.ndarray:
    image = np.full((200, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (180, 180), (0, 0, 0), 3)
    return image


def _add_page_with_result(window: MainWindow, result: PageResult) -> None:
    window._add_image_paths([result.input_path])
    window._results_by_input[str(result.input_path.resolve())] = result


def test_diagram_page_shows_dedicated_message_instead_of_unprocessed(qtbot, tmp_path):
    """DIA-3: 도형 페이지는 '아직 처리되지 않았습니다'가 아니라 전용 안내 문구를 보여준다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "diagram.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    result = PageResult(
        input_path=image_path,
        page_pdf_path=pdf_path,
        text=None,
        document_type=DocumentType.DIAGRAM,
        sharpened_image=_make_diagram_image(),
    )
    _add_page_with_result(window, result)

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    assert window.text_review_edit.isEnabled() is False
    assert (
        window.text_review_edit.placeholderText()
        == "이 페이지는 도형으로 분류되어 텍스트 검수 대상이 아닙니다."
    )
    assert window.vectorize_button.isEnabled() is True


def test_text_page_keeps_review_enabled_and_disables_vectorize_button(qtbot, tmp_path):
    """텍스트 페이지에서는 검수 패널이 그대로 동작하고 벡터화 버튼은 비활성화되어야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "text.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "text.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    result = PageResult(
        input_path=image_path,
        page_pdf_path=pdf_path,
        text="인식된 텍스트",
        document_type=DocumentType.TEXT,
    )
    _add_page_with_result(window, result)

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    assert window.text_review_edit.isEnabled() is True
    assert window.text_review_edit.toPlainText() == "인식된 텍스트"
    assert window.vectorize_button.isEnabled() is False


def test_vectorize_button_creates_svg_and_exposes_disclaimer(qtbot, tmp_path, monkeypatch):
    """DIA-2/DIA-3: 벡터화 버튼을 누르면 SVG가 생성되고, 한계 고지 문구가 팝업과
    상시 라벨 양쪽에 실제로 노출되어야 한다(로그로만 남기는 것은 불충분)."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "diagram.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    result = PageResult(
        input_path=image_path,
        page_pdf_path=pdf_path,
        text=None,
        document_type=DocumentType.DIAGRAM,
        sharpened_image=_make_diagram_image(),
    )
    _add_page_with_result(window, result)
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    shown_messages: list[str] = []
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.information",
        lambda *args, **kwargs: shown_messages.append(args[-1]),
    )

    qtbot.mouseClick(window.vectorize_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: result.svg_path is not None, timeout=15000)

    assert result.svg_path.exists()
    assert result.vectorization_disclaimer == VECTORIZATION_DISCLAIMER
    assert shown_messages and shown_messages[-1] == VECTORIZATION_DISCLAIMER
    assert window.vectorization_disclaimer_label.text() == VECTORIZATION_DISCLAIMER
