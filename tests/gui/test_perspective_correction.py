"""PRE-1(GUI 수동 코너 오버라이드) 수용 기준 검증.

실제 파이프라인(Tesseract 등)을 태우지 않고도 검증할 수 있는 것들만 다룬다 —
`ReprocessWorker.run()`을 가짜로 대체해 "어떤 `preprocess_config`로 시작됐는지",
"버튼 가드가 워커 실행 상태를 따라가는지", "대칭적 필드 보존이 지켜지는지"만
확인한다. 실제 파이프라인을 끝까지 태우는 통합 검증은
`tests/gui/test_crop_rotate_reprocess.py`와 동일하게 외부 바이너리가 있어야
하므로 이 파일의 범위 밖이다.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pymupdf
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QDialog

from app.gui.crop_rotate_dialog import CropRotateDialog, PerspectiveCorrectionDialog
from app.gui.main_window import MainWindow
from app.gui.worker import PageResult, ReprocessWorker
from app.router.classifier import DocumentType


def _write_minimal_valid_pdf(pdf_path: Path) -> None:
    """가짜 바이트 대신 진짜로 열리는 최소 1페이지 PDF를 만든다.

    `_on_reprocess_finished`는 재처리 완료 후 `_rebuild_merged_pdf()`(`pymupdf.open`)를
    호출하므로, 내용이 없는 가짜 바이트를 그대로 쓰면 병합이 예외로 실패해
    `QMessageBox.warning`(모달) 팝업이 떠 테스트가 멈춘다.
    """
    doc = pymupdf.open()
    try:
        doc.new_page()
        doc.save(pdf_path)
    finally:
        doc.close()


class _BlockingThread(QThread):
    """`isRunning()`이 확실히 `True`를 반환하도록 멈춰 있는 가짜 워커
    (`tests/gui/test_crop_rotate_guards.py`와 동일한 패턴)."""

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


def _add_page_with_result(window: MainWindow, result: PageResult) -> None:
    window._add_image_paths([result.input_path])
    window._results_by_input[str(result.input_path.resolve())] = result


class _CapturingReprocessWorker(ReprocessWorker):
    """실제 파이프라인(`process_page_image`)을 태우지 않고 즉시 성공한 것처럼
    동작하는 가짜 `ReprocessWorker`. 생성된 인스턴스를 모두 `created` 리스트에
    남겨, 호출부가 실제로 어떤 `preprocess_config`/`type_override`로 워커를
    만들었는지 검증할 수 있게 한다."""

    created: list["_CapturingReprocessWorker"] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _CapturingReprocessWorker.created.append(self)

    def run(self) -> None:
        self.page_result = PageResult(
            input_path=self.input_path,
            page_pdf_path=self.page_pdf_path,
            text="dummy",
            document_type=DocumentType.TEXT,
        )


def _setup_window_with_processed_page(qtbot, tmp_path) -> tuple[MainWindow, PageResult]:
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "page.pdf"
    _write_minimal_valid_pdf(pdf_path)
    result = PageResult(
        input_path=image_path,
        page_pdf_path=pdf_path,
        text="텍스트",
        document_type=DocumentType.TEXT,
    )
    _add_page_with_result(window, result)
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    return window, result


def test_perspective_correction_button_disabled_while_batch_processing(qtbot, tmp_path):
    """(b) 배치/재처리 중에는 "원근 보정(수동)" 버튼도 기존 자르기/회전 버튼과
    동일하게 비활성화돼야 한다."""
    window, result = _setup_window_with_processed_page(qtbot, tmp_path)

    window._refresh_manual_correction_controls(result.input_path)
    assert window.perspective_correction_button.isEnabled() is True

    batch_thread = _start_blocking_thread(qtbot)
    try:
        window._worker = batch_thread
        window._refresh_manual_correction_controls(result.input_path)
        assert window.perspective_correction_button.isEnabled() is False
    finally:
        _stop_blocking_thread(batch_thread)
        window._worker = None

    window._refresh_manual_correction_controls(result.input_path)
    assert window.perspective_correction_button.isEnabled() is True


def test_perspective_correction_button_disabled_while_reprocessing(qtbot, tmp_path):
    """(b) 연장: 재처리가 이미 실행 중일 때도 비활성화돼야 한다."""
    window, result = _setup_window_with_processed_page(qtbot, tmp_path)

    reprocess_thread = _start_blocking_thread(qtbot)
    try:
        window._reprocess_worker = reprocess_thread
        window._refresh_manual_correction_controls(result.input_path)
        assert window.perspective_correction_button.isEnabled() is False
    finally:
        _stop_blocking_thread(reprocess_thread)
        window._reprocess_worker = None


def test_perspective_correction_apply_starts_worker_with_manual_corners(
    qtbot, tmp_path, monkeypatch
):
    """(a) 다이얼로그에서 지정한 좌표 → 적용 → `ReprocessWorker`가 실제로
    `preprocess_config.corners`를 채운 채로(그리고 `skip_perspective_on_failure=False`로)
    시작되는지 확인한다."""
    window, result = _setup_window_with_processed_page(qtbot, tmp_path)

    _CapturingReprocessWorker.created.clear()
    monkeypatch.setattr("app.gui.main_window.ReprocessWorker", _CapturingReprocessWorker)
    monkeypatch.setattr(
        "app.gui.main_window.load_image_bgr",
        lambda *_args, **_kwargs: np.zeros((50, 40, 3), dtype=np.uint8),
    )

    chosen_corners = np.array([[1, 2], [30, 3], [31, 40], [0, 41]], dtype=np.float32)

    def fake_exec(self):
        for x_spin, y_spin, (x, y) in zip(self._x_spins, self._y_spins, chosen_corners):
            x_spin.setValue(int(x))
            y_spin.setValue(int(y))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PerspectiveCorrectionDialog, "exec", fake_exec)

    window._on_perspective_correction_clicked()
    qtbot.waitUntil(lambda: window._reprocess_worker is None, timeout=5000)

    assert len(_CapturingReprocessWorker.created) == 1
    started_worker = _CapturingReprocessWorker.created[0]
    assert started_worker._preprocess_config is not None
    assert started_worker._preprocess_config.skip_perspective_on_failure is False
    np.testing.assert_array_equal(started_worker._preprocess_config.corners, chosen_corners)

    updated_result = window._results_by_input[str(result.input_path.resolve())]
    np.testing.assert_array_equal(updated_result.corners, chosen_corners)


def test_manual_corners_survive_crop_rotate_reprocess(qtbot, tmp_path, monkeypatch):
    """(c) 대칭 보존 회귀 테스트: 수동 코너를 지정한 뒤 자르기/회전만 다시
    적용해도 `PageResult.corners`가 사라지면 안 된다."""
    window, result = _setup_window_with_processed_page(qtbot, tmp_path)
    manual_corners = np.array([[5, 5], [90, 6], [88, 95], [4, 94]], dtype=np.float32)
    result.corners = manual_corners
    window._results_by_input[str(result.input_path.resolve())] = result

    _CapturingReprocessWorker.created.clear()
    monkeypatch.setattr("app.gui.main_window.ReprocessWorker", _CapturingReprocessWorker)

    def fake_crop_rotate_exec(self):
        self.x_spin.setValue(0)
        self.y_spin.setValue(0)
        self.width_spin.setValue(self.width_spin.maximum())
        self.height_spin.setValue(self.height_spin.maximum())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CropRotateDialog, "exec", fake_crop_rotate_exec)
    monkeypatch.setattr(
        "app.gui.main_window.load_image_bgr",
        lambda *_args, **_kwargs: np.zeros((100, 100, 3), dtype=np.uint8),
    )

    window._on_crop_rotate_clicked()
    qtbot.waitUntil(lambda: window._reprocess_worker is None, timeout=5000)

    assert len(_CapturingReprocessWorker.created) == 1
    started_worker = _CapturingReprocessWorker.created[0]
    assert started_worker._preprocess_config is not None
    np.testing.assert_array_equal(started_worker._preprocess_config.corners, manual_corners)

    updated_result = window._results_by_input[str(result.input_path.resolve())]
    np.testing.assert_array_equal(updated_result.corners, manual_corners)


def test_manual_corners_discarded_when_new_crop_changes_image_size(
    qtbot, tmp_path, monkeypatch
):
    """(HIGH, code-reviewer 지적) 회귀 테스트: 이전에 지정한 코너가 새 자르기로
    바뀐 이미지 크기 범위를 벗어나면, 손상된(대부분 검은) 이미지를 만들어내는
    `PreprocessConfig(corners=...)`로 그대로 넘기는 대신 폐기하고 자동 검출로
    안전하게 폴백해야 한다."""
    window, result = _setup_window_with_processed_page(qtbot, tmp_path)
    # 100x100 기준으로 지정했던 코너 — 새 자르기 결과(40x40)에는 맞지 않는다.
    manual_corners = np.array([[5, 5], [90, 6], [88, 95], [4, 94]], dtype=np.float32)
    result.corners = manual_corners
    window._results_by_input[str(result.input_path.resolve())] = result

    _CapturingReprocessWorker.created.clear()
    monkeypatch.setattr("app.gui.main_window.ReprocessWorker", _CapturingReprocessWorker)

    def fake_crop_rotate_exec(self):
        self.x_spin.setValue(0)
        self.y_spin.setValue(0)
        self.width_spin.setValue(40)
        self.height_spin.setValue(40)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CropRotateDialog, "exec", fake_crop_rotate_exec)
    # 자르기 대상 원본 이미지 자체는 여전히 100x100이지만, 이번에 지정한 자르기
    # 영역(40x40)이 이전 코너 좌표(최대 90/95)보다 작아 결과 이미지 크기가 달라진다.
    monkeypatch.setattr(
        "app.gui.main_window.load_image_bgr",
        lambda *_args, **_kwargs: np.zeros((100, 100, 3), dtype=np.uint8),
    )

    window._on_crop_rotate_clicked()
    qtbot.waitUntil(lambda: window._reprocess_worker is None, timeout=5000)

    assert len(_CapturingReprocessWorker.created) == 1
    started_worker = _CapturingReprocessWorker.created[0]
    # 손상된 이미지를 만들어내는 범위 밖 corners로 워커가 시작되면 안 된다 —
    # 자동 검출(기본 `PreprocessConfig`)로 폴백해야 한다.
    assert started_worker._preprocess_config is None

    updated_result = window._results_by_input[str(result.input_path.resolve())]
    # 폐기된 코너는 다음 `PageResult`에도 이어지면 안 된다(안 그러면 다음 재처리
    # 때마다 같은 무효 좌표가 계속 폐기 시도를 반복한다).
    assert updated_result.corners is None


def test_manual_corners_survive_type_override_reprocess(qtbot, tmp_path, monkeypatch):
    """(c) 대칭 보존 회귀 테스트: 수동 코너를 지정한 뒤 문서 유형만 다시
    적용해도 `PageResult.corners`가 사라지면 안 된다."""
    window, result = _setup_window_with_processed_page(qtbot, tmp_path)
    manual_corners = np.array([[5, 5], [90, 6], [88, 95], [4, 94]], dtype=np.float32)
    result.corners = manual_corners
    window._results_by_input[str(result.input_path.resolve())] = result

    _CapturingReprocessWorker.created.clear()
    monkeypatch.setattr("app.gui.main_window.ReprocessWorker", _CapturingReprocessWorker)
    monkeypatch.setattr(
        "app.gui.main_window.load_image_bgr",
        lambda *_args, **_kwargs: np.zeros((100, 100, 3), dtype=np.uint8),
    )

    index = window.type_override_combo.findData(DocumentType.DIAGRAM)
    window.type_override_combo.setCurrentIndex(index)

    window._on_type_override_apply_clicked()
    qtbot.waitUntil(lambda: window._reprocess_worker is None, timeout=5000)

    assert len(_CapturingReprocessWorker.created) == 1
    started_worker = _CapturingReprocessWorker.created[0]
    assert started_worker._preprocess_config is not None
    np.testing.assert_array_equal(started_worker._preprocess_config.corners, manual_corners)

    updated_result = window._results_by_input[str(result.input_path.resolve())]
    np.testing.assert_array_equal(updated_result.corners, manual_corners)
    assert updated_result.type_override == DocumentType.DIAGRAM
