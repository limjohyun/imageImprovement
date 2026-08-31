"""Phase4-3(PDF-2) 수용 기준 검증: 페이지 재정렬(드래그 앤 드롭)/삭제.

실제 사용자 드래그 제스처는 헤드리스(offscreen) 환경에서 재현이 매우 불안정하므로,
Qt가 내부적으로 드래그 앤 드롭 재정렬 시 호출하는 것과 동일한 모델 API
(`QAbstractItemModel.moveRow`, 실제로 `rowsMoved` 시그널을 발생시킨다)를 직접 호출해
"드롭 이후" 상태를 재현한다. 이는 회피가 아니라 검증 대상(재정렬 이후 병합 PDF 갱신
로직)에 정확히 대응하는 방식이다 — `_build_file_list_column`이 등록한 실제
`rowsMoved` 연결(`self._on_rows_moved`)이 그대로 호출된다.
"""

from __future__ import annotations

import threading

import pymupdf
import pytest
from PySide6.QtCore import QModelIndex, QThread
from PySide6.QtWidgets import QAbstractItemView

from app.gui.main_window import MainWindow
from app.gui.worker import PageResult, ProcessingWorker


class _BlockingThread(QThread):
    """`isRunning()`이 확실히 `True`를 반환하는 가짜 워커(`test_crop_rotate_guards.py`와 동일)."""

    def __init__(self) -> None:
        super().__init__()
        self._stop_event = threading.Event()

    def run(self) -> None:
        self._stop_event.wait()

    def stop(self) -> None:
        self._stop_event.set()


def _start_blocking_thread(qtbot) -> _BlockingThread:
    thread = _BlockingThread()
    thread.start()
    qtbot.waitUntil(thread.isRunning, timeout=2000)
    return thread


def _stop_blocking_thread(thread: _BlockingThread) -> None:
    thread.stop()
    thread.wait()


def _write_labelled_pdf(path, label: str) -> None:
    """`label` 텍스트만 담은 단일 페이지 PDF를 만든다(병합 후 페이지 순서 확인용)."""
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 40), label)
    doc.save(path)
    doc.close()


def _merged_pdf_page_labels(pdf_path) -> list[str]:
    with pymupdf.open(pdf_path) as doc:
        return [page.get_text().strip() for page in doc]


def _add_processed_page(window: MainWindow, tmp_path, name: str) -> PageResult:
    image_path = tmp_path / f"{name}.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / f"{name}.pdf"
    _write_labelled_pdf(pdf_path, name)
    result = PageResult(input_path=image_path, page_pdf_path=pdf_path, text=name)
    window._add_image_paths([image_path])
    window._results_by_input[str(image_path.resolve())] = result
    return result


# ----------------------------------------------------------------------
# 재정렬
# ----------------------------------------------------------------------


def test_drag_reorder_rebuilds_merged_pdf_in_new_order(qtbot, tmp_path):
    """PDF-2: 드래그로 순서를 바꾸면 최종 병합 PDF가 새 순서를 반영해야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    _add_processed_page(window, tmp_path, "page_a")
    _add_processed_page(window, tmp_path, "page_b")
    window._rebuild_merged_pdf()

    assert window._merged_pdf_path is not None
    assert _merged_pdf_page_labels(window._merged_pdf_path) == ["page_a", "page_b"]

    # Qt가 내부 드래그 앤 드롭 재정렬 시 실제로 호출하는 모델 API. 0번 행을 2번째
    # 자리(현재 1번 행 뒤)로 옮겨 순서를 뒤집는다 — `rowsMoved`가 실제로 발생하므로
    # `_build_file_list_column`에서 연결한 `_on_rows_moved`가 그대로 호출된다.
    model = window.file_list_widget.model()
    moved = model.moveRow(QModelIndex(), 0, QModelIndex(), 2)
    assert moved is True
    assert [p.name for p in window._image_paths_in_list()] == ["page_b.png", "page_a.png"]

    assert _merged_pdf_page_labels(window._merged_pdf_path) == ["page_b", "page_a"]


def test_drag_reorder_without_processed_pages_does_not_touch_merged_pdf(qtbot, tmp_path):
    """아직 아무 페이지도 처리되지 않았다면(`_merged_pdf_path is None`) 재정렬해도
    재병합을 시도하지 않는다(병합할 대상 자체가 없다)."""
    window = MainWindow()
    qtbot.addWidget(window)

    page_a = tmp_path / "page_a.png"
    page_b = tmp_path / "page_b.png"
    page_a.write_bytes(b"fake-image-bytes")
    page_b.write_bytes(b"fake-image-bytes")
    window._add_image_paths([page_a, page_b])

    model = window.file_list_widget.model()
    model.moveRow(QModelIndex(), 0, QModelIndex(), 2)

    assert window._merged_pdf_path is None


def test_start_processing_disables_editing_immediately_after_start(qtbot, tmp_path, monkeypatch):
    """code-reviewer HIGH 지적 회귀 테스트.

    `_start_processing()`이 실제로 실행하는 순서를 그대로 검증한다 — 이전에는
    `_refresh_list_editing_controls()`가 `worker.start()` *이전*에 호출되어
    `QThread.isRunning()`이 항상 `False`로 보였고(아직 시작 전이므로), 그 결과
    배치 처리가 진행 중인데도 드래그/삭제가 막히지 않는 조용한 버그가 있었다.
    `ProcessingWorker.run`을 몽치패치해 실제 파이프라인 대신 이벤트로 멈춰 있게
    만들고, `_start_processing()`을 직접 호출해 `.start()` 직후 시점의 상태를
    확인한다.
    """
    stop_event = threading.Event()
    started_event = threading.Event()

    def _blocking_run(self) -> None:
        started_event.set()
        stop_event.wait()

    monkeypatch.setattr(ProcessingWorker, "run", _blocking_run)

    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "page_a.png"
    image_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([image_path])

    try:
        window._start_processing()
        qtbot.waitUntil(started_event.is_set, timeout=2000)

        assert window._worker is not None
        assert window._worker.isRunning() is True
        assert (
            window.file_list_widget.dragDropMode()
            == QAbstractItemView.DragDropMode.NoDragDrop
        )

        window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
        assert window.delete_page_button.isEnabled() is False
    finally:
        stop_event.set()
        if window._worker is not None:
            window._worker.wait()


def test_drag_disabled_while_worker_running(qtbot):
    """워커가 실행 중이면 재정렬(드래그) 자체를 막는다 — 진행 중인 작업이 참조하는
    페이지 경로/인덱스가 목록 변경으로 어긋나는 것을 막기 위해서다."""
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.file_list_widget.dragDropMode() == QAbstractItemView.DragDropMode.InternalMove

    thread = _start_blocking_thread(qtbot)
    try:
        window._worker = thread
        window._refresh_list_editing_controls()
        assert window.file_list_widget.dragDropMode() == QAbstractItemView.DragDropMode.NoDragDrop
    finally:
        _stop_blocking_thread(thread)
        window._worker = None

    window._refresh_list_editing_controls()
    assert window.file_list_widget.dragDropMode() == QAbstractItemView.DragDropMode.InternalMove


def test_on_rows_moved_skips_rebuild_while_worker_running(qtbot, tmp_path):
    """드래그가 비활성화돼 있어도(방어적으로) `_on_rows_moved`가 직접 불리는 경우까지
    대비해, 워커 실행 중이면 재병합을 건너뛰어야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    _add_processed_page(window, tmp_path, "page_a")
    _add_processed_page(window, tmp_path, "page_b")
    window._rebuild_merged_pdf()
    before = window._merged_pdf_path
    assert before is not None

    thread = _start_blocking_thread(qtbot)
    try:
        window._worker = thread
        window._on_rows_moved()
        assert window._merged_pdf_path == before
    finally:
        _stop_blocking_thread(thread)
        window._worker = None


# ----------------------------------------------------------------------
# 삭제
# ----------------------------------------------------------------------


def test_delete_selected_page_removes_from_list_and_results(qtbot, tmp_path):
    """PDF-2: 선택한 페이지를 삭제하면 목록과 결과 캐시에서 모두 제거되고, 남은
    페이지만으로 최종 병합 PDF가 다시 만들어진다."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    result_a = _add_processed_page(window, tmp_path, "page_a")
    _add_processed_page(window, tmp_path, "page_b")
    window._rebuild_merged_pdf()

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert window.delete_page_button.isEnabled() is True

    window._on_delete_pages_clicked()

    assert window.file_list_widget.count() == 1
    assert [p.name for p in window._image_paths_in_list()] == ["page_b.png"]
    assert str(result_a.input_path.resolve()) not in window._results_by_input
    assert _merged_pdf_page_labels(window._merged_pdf_path) == ["page_b"]


def test_delete_last_page_resets_to_initial_state(qtbot, tmp_path):
    """요구사항 4: 마지막 페이지를 삭제하면 GUI-1 이전 상태로 돌아가고, 저장 버튼도
    비활성화되며 크래시가 없어야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    _add_processed_page(window, tmp_path, "page_a")
    window._rebuild_merged_pdf()
    assert window.save_button.isEnabled() is True

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    window._on_delete_pages_clicked()

    assert window.file_list_widget.count() == 0
    assert window._merged_pdf_path is None
    assert window.save_button.isEnabled() is False
    assert window.status_label.text() == "이미지를 추가하세요."
    assert window.text_review_edit.isEnabled() is False
    assert window.crop_rotate_button.isEnabled() is False
    assert window.delete_page_button.isEnabled() is False


def test_delete_without_processed_pages_leaves_merged_pdf_none(qtbot, tmp_path):
    """아직 처리되지 않은 페이지만 있을 때 하나를 지워도 `_merged_pdf_path`는
    계속 `None`이어야 한다(처음부터 저장할 결과가 없었다)."""
    window = MainWindow()
    qtbot.addWidget(window)

    page_a = tmp_path / "page_a.png"
    page_b = tmp_path / "page_b.png"
    page_a.write_bytes(b"fake-image-bytes")
    page_b.write_bytes(b"fake-image-bytes")
    window._add_image_paths([page_a, page_b])

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    window._on_delete_pages_clicked()

    assert window.file_list_widget.count() == 1
    assert window._merged_pdf_path is None


def test_delete_blocked_while_worker_running(qtbot, tmp_path, monkeypatch):
    """워커 실행 중에는 삭제를 막고 경고를 띄운다."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    _add_processed_page(window, tmp_path, "page_a")
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    warnings: list[str] = []
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[-1]),
    )

    thread = _start_blocking_thread(qtbot)
    try:
        window._reprocess_worker = thread
        window._on_delete_pages_clicked()
        assert warnings, "워커 실행 중에는 경고를 띄워야 한다."
        assert window.file_list_widget.count() == 1, "삭제가 실제로 실행되면 안 된다."
    finally:
        _stop_blocking_thread(thread)
        window._reprocess_worker = None


def test_delete_button_disabled_without_selection(qtbot, tmp_path):
    """선택된 페이지가 없으면 삭제 버튼이 비활성화돼야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.delete_page_button.isEnabled() is False

    image_path = tmp_path / "page_a.png"
    image_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([image_path])
    assert window.delete_page_button.isEnabled() is False

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert window.delete_page_button.isEnabled() is True

    window.file_list_widget.clearSelection()
    assert window.delete_page_button.isEnabled() is False


def test_delete_button_disabled_while_worker_running_even_with_selection(qtbot, tmp_path):
    """워커 실행 중이면 선택된 페이지가 있어도 삭제 버튼이 비활성화돼야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "page_a.png"
    image_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([image_path])
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert window.delete_page_button.isEnabled() is True

    thread = _start_blocking_thread(qtbot)
    try:
        window._vectorize_worker = thread
        window._refresh_list_editing_controls()
        assert window.delete_page_button.isEnabled() is False
    finally:
        _stop_blocking_thread(thread)
        window._vectorize_worker = None


@pytest.mark.parametrize("key_name", ["Key_Delete", "Key_Backspace"])
def test_delete_keyboard_shortcut_removes_selected_page(qtbot, tmp_path, key_name):
    """`Delete`/`Backspace` 키로도 선택된 페이지를 삭제할 수 있어야 한다(macOS 키보드는
    물리적으로 Backspace만 있는 경우가 많다)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.activateWindow()

    image_path = tmp_path / "page_a.png"
    image_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([image_path])
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    window.file_list_widget.setFocus()
    qtbot.waitUntil(window.file_list_widget.hasFocus, timeout=2000)

    key = getattr(Qt.Key, key_name)
    QTest.keyClick(window.file_list_widget, key)

    assert window.file_list_widget.count() == 0
