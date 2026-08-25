"""Phase1-5 수용 기준 검증: `MainWindow` 위젯 동작.

GUI-1(폴더/다중 파일 입력), 처리 파이프라인의 QThread 비블로킹 여부, GUI-4(저장)를
확인한다. GUI-2(미리보기)는 렌더링 헬퍼(`render_pdf_first_page_to_pixmap`)를 별도로
검증한다. 다이얼로그(`QFileDialog`)는 실제로 띄우지 않고 내부 메서드를 직접
호출하거나 `monkeypatch`로 대체해 headless(`QT_QPA_PLATFORM=offscreen`) 환경에서도
동작하게 한다.
"""

from __future__ import annotations

import shutil

import cv2
import pymupdf
import pytest
from PySide6.QtCore import Qt, QThread, Signal

from app.gui.main_window import MainWindow, render_pdf_first_page_to_pixmap
from app.gui.worker import PageResult

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None
_PIPELINE_AVAILABLE = _TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE

_PIPELINE_SKIP_REASON = "tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다."


def test_main_window_can_be_created(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "이미지 → PDF 변환"
    assert window.file_list_widget.count() == 0
    assert window.save_button.isEnabled() is False


def test_add_image_paths_populates_list_without_duplicates(qtbot, tmp_path):
    """GUI-1: 선택된 이미지가 목록에 쌓이고, 같은 파일을 다시 추가해도 중복되지 않는다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image-bytes")

    window._add_image_paths([image_path])
    window._add_image_paths([image_path])

    assert window.file_list_widget.count() == 1
    assert window._image_paths_in_list() == [image_path.resolve()]


def test_add_image_paths_uses_natural_sort_order(qtbot, tmp_path):
    """PDF-1(입력 순서대로 병합): 사전식 정렬(page1, page10, page2 ...)이 아니라
    파일명 안 숫자 크기를 기준으로 자연 정렬되어야 페이지 순서가 뒤섞이지 않는다."""
    window = MainWindow()
    qtbot.addWidget(window)

    names = ["page2.png", "page10.png", "page1.png"]
    paths = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"fake-image-bytes")
        paths.append(path)

    # 폴더 스캔은 사전식 정렬 결과를 넘길 수 있으므로, 이미 뒤섞인 순서로 들어와도
    # `_add_image_paths` 내부에서 자연 정렬되어야 한다.
    window._add_image_paths(sorted(paths))

    assert [p.name for p in window._image_paths_in_list()] == [
        "page1.png",
        "page2.png",
        "page10.png",
    ]


def test_text_review_disabled_when_nothing_selected(qtbot):
    """TXT-3: 아무 페이지도 선택하지 않은 초기 상태에서는 검수 위젯이 비활성화·비어 있다."""
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.text_review_edit.isEnabled() is False
    assert window.text_review_edit.toPlainText() == ""


def test_text_review_disabled_for_unprocessed_page(qtbot, tmp_path):
    """TXT-3: 아직 처리되지 않은 페이지를 선택하면 검수 위젯은 비활성화·비어 있어야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "page1.png"
    image_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([image_path])

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    assert window.text_review_edit.isEnabled() is False
    assert window.text_review_edit.toPlainText() == ""
    assert window.text_review_edit.placeholderText() == "아직 처리되지 않았습니다."


def test_text_review_edit_persists_across_selection_change(qtbot, tmp_path):
    """TXT-3: 처리된 페이지 선택 시 OCR 텍스트가 채워지고, 사용자가 수정한 내용은
    `PageResult.text`에 즉시 반영되며 다른 페이지로 옮겼다 돌아와도 유실되지 않는다."""
    window = MainWindow()
    qtbot.addWidget(window)

    page1_path = tmp_path / "page1.png"
    page2_path = tmp_path / "page2.png"
    page1_path.write_bytes(b"fake-image-bytes")
    page2_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([page1_path, page2_path])

    result1 = PageResult(
        input_path=page1_path, page_pdf_path=tmp_path / "page1.pdf", text="첫 페이지 텍스트"
    )
    result2 = PageResult(
        input_path=page2_path, page_pdf_path=tmp_path / "page2.pdf", text="둘째 페이지 텍스트"
    )
    window._results_by_input[str(page1_path.resolve())] = result1
    window._results_by_input[str(page2_path.resolve())] = result2

    item1 = window.file_list_widget.item(0)
    item2 = window.file_list_widget.item(1)
    assert item1.data(Qt.ItemDataRole.UserRole) == str(page1_path.resolve())

    # 첫 페이지를 선택하면 검수 위젯이 활성화되고 OCR 텍스트가 채워진다.
    window.file_list_widget.setCurrentItem(item1)
    assert window.text_review_edit.isEnabled() is True
    assert window.text_review_edit.toPlainText() == "첫 페이지 텍스트"

    # 사용자가 텍스트를 수정하면 즉시 PageResult.text에 반영된다.
    edited_text = "사용자가 수정한 첫 페이지 텍스트"
    window.text_review_edit.setPlainText(edited_text)
    assert result1.text == edited_text

    # 다른 페이지로 옮기면 그 페이지의 텍스트로 바뀐다(첫 페이지 원본 텍스트가 덮어써지지 않는다).
    window.file_list_widget.setCurrentItem(item2)
    assert window.text_review_edit.toPlainText() == "둘째 페이지 텍스트"
    assert result1.text == edited_text  # 다른 페이지를 보는 동안에도 수정 내용은 유지된다.

    # 다시 첫 페이지로 돌아오면 수정한 내용이 그대로 남아 있어야 한다(데이터 유실 없음).
    window.file_list_widget.setCurrentItem(item1)
    assert window.text_review_edit.toPlainText() == edited_text
    assert result1.text == edited_text


def test_start_processing_resets_text_review_panel(qtbot, tmp_path, monkeypatch):
    """TXT-3(선택): 새 배치 처리를 시작하면 이전 검수 내용이 초기화된다.

    실제 파이프라인(Tesseract 등) 없이도 항상 실행되도록 `ProcessingWorker`를
    아무 작업도 하지 않는 가짜 QThread로 대체한다.
    """

    class _FakeWorker(QThread):
        progress_changed = Signal(int, int)
        page_processed = Signal(object)
        error_occurred = Signal(str)

        def __init__(self, image_paths, work_dir, *, lang=None, parent=None):
            super().__init__(parent)
            self.merged_pdf_path = None

        def run(self) -> None:
            pass  # 아무 것도 하지 않고 즉시 끝난다.

    monkeypatch.setattr("app.gui.main_window.ProcessingWorker", _FakeWorker)

    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "page1.png"
    image_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([image_path])

    # 이전에 어떤 페이지를 검수하고 있었던 상태를 흉내낸다.
    window._reviewed_input_path = image_path
    window.text_review_edit.setEnabled(True)
    window.text_review_edit.setPlainText("이전 페이지의 텍스트")

    with qtbot.waitSignal(window.processing_completed, timeout=5000):
        window._start_processing()
        # 검수 위젯 초기화는 워커 스레드 시작 전, 이 시점에 이미 끝나 있어야 한다.
        assert window._reviewed_input_path is None
        assert window.text_review_edit.toPlainText() == ""
        assert window.text_review_edit.isEnabled() is False


@pytest.mark.skipif(not _PIPELINE_AVAILABLE, reason=_PIPELINE_SKIP_REASON)
def test_text_review_populates_with_ocr_text_after_processing(
    qtbot, tmp_path, synthetic_text_photo
):
    """TXT-3: 실제 파이프라인 처리 완료 후 페이지를 선택하면 OCR 인식 텍스트가 검수
    위젯에 채워진다."""
    image_path = tmp_path / "page1.png"
    cv2.imwrite(str(image_path), synthetic_text_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)
    window._add_image_paths([image_path])

    with qtbot.waitSignal(window.processing_completed, timeout=120000):
        window._start_processing()

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    result = window._results_by_input[str(image_path.resolve())]
    assert window.text_review_edit.isEnabled() is True
    assert window.text_review_edit.toPlainText() == result.text
    assert window.text_review_edit.toPlainText().strip() != ""


@pytest.mark.skipif(not _PIPELINE_AVAILABLE, reason=_PIPELINE_SKIP_REASON)
def test_start_processing_runs_in_background_and_enables_save(
    qtbot, tmp_path, synthetic_text_photo
):
    """처리 시작 직후에도 UI 제어권이 즉시 돌아오고(QThread), 완료 후 저장 버튼이 켜져야 한다."""
    image_path = tmp_path / "page1.png"
    cv2.imwrite(str(image_path), synthetic_text_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)
    window._add_image_paths([image_path])

    with qtbot.waitSignal(window.processing_completed, timeout=120000):
        window._start_processing()
        # 처리 시작 직후 스레드가 끝나길 기다리지 않고 곧바로 이 지점에 도달해야 한다.
        assert window.process_button.isEnabled() is False

    assert window.save_button.isEnabled() is True
    assert window._merged_pdf_path is not None
    assert window._merged_pdf_path.exists()
    with pymupdf.open(window._merged_pdf_path) as doc:
        assert doc.page_count == 1


@pytest.mark.skipif(not _PIPELINE_AVAILABLE, reason=_PIPELINE_SKIP_REASON)
def test_save_result_writes_pdf_to_chosen_path(qtbot, tmp_path, monkeypatch, synthetic_text_photo):
    """GUI-4: 저장 버튼을 누르면 사용자가 지정한 경로에 최종 PDF가 실제로 생성된다."""
    image_path = tmp_path / "page1.png"
    cv2.imwrite(str(image_path), synthetic_text_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)
    window._add_image_paths([image_path])

    with qtbot.waitSignal(window.processing_completed, timeout=120000):
        window._start_processing()

    destination = tmp_path / "final_output.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )

    window._on_save_clicked()

    assert destination.exists()
    with pymupdf.open(destination) as doc:
        assert doc.page_count == 1


def test_render_pdf_first_page_to_pixmap_returns_non_null_pixmap(qtbot, tmp_path):
    """GUI-2 미리보기 렌더링 헬퍼가 PDF 첫 페이지를 유효한 QPixmap으로 변환해야 한다."""
    pdf_path = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 40), "테스트 페이지")
    doc.save(pdf_path)
    doc.close()

    pixmap = render_pdf_first_page_to_pixmap(pdf_path)

    assert not pixmap.isNull()
    assert pixmap.width() > 0
    assert pixmap.height() > 0
