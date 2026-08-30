"""Phase4-1(GUI-3 일부) code-reviewer 지적 사항에 대한 회귀 테스트.

`tests/gui/test_crop_rotate_reprocess.py`는 실제 파이프라인(Tesseract 등)이 있어야
동작하지만, 여기서 다루는 문제들은 실제 파이프라인 없이도(가짜 `QThread`만으로)
재현/검증할 수 있는 "워커 실행 상태 조합에 따른 버튼/가드 로직"이므로 별도 파일로
분리하고 외부 바이너리 skip 마커를 두지 않는다.

- HIGH #1: 배치 처리(`ProcessingWorker`) 또는 재처리(`ReprocessWorker`)가 실행 중이면
  이미 처리된 페이지라도 "자르기/회전" 버튼이 비활성화돼야 한다. 그렇지 않으면 배치가
  `merged.pdf`를 쓰는 동안 재처리 완료 콜백도 같은 파일을 동시에 써서 경합이 생긴다.
- HIGH #2: 배치/벡터화/재처리 중 어느 하나라도 실행 중이면 "처리 시작"이 다시 눌려도
  `_start_processing()`이 새 배치를 시작하면 안 된다(안 그러면 실행 중인 워커가 쓰려는
  임시 작업 디렉터리가 지워진다).
- MEDIUM #3: `ReprocessWorker.finished`가 GUI 스레드에서 처리되는 시점과 실제 스레드
  종료 사이의 틈에 사용자가 같은 페이지의 재처리를 다시 시작해도, 뒤늦게 도착한 예전
  워커의 콜백이 이미 시작된 새 워커의 참조(`self._reprocess_worker`)를 지우면 안 된다.
"""

from __future__ import annotations

import threading

import numpy as np
from PySide6.QtCore import QThread

from app.gui.main_window import MainWindow
from app.gui.worker import PageResult, ReprocessWorker


class _BlockingThread(QThread):
    """`isRunning()`이 확실히 `True`를 반환하도록, 신호를 받을 때까지 멈춰 있는 가짜 워커.

    `unittest.mock.Mock(isRunning=...)`으로도 흉내낼 수 있지만, 실제 `QThread.start()`/
    `isRunning()`/`wait()` 동작 자체를 검증하기 위해 진짜 `QThread`를 그대로 쓴다.
    """

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


def test_crop_rotate_button_disabled_while_batch_processing(qtbot, tmp_path):
    """HIGH #1: 페이지가 이미 처리됐어도 배치 처리가 실행 중이면 버튼이 비활성화돼야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "page.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    result = PageResult(input_path=image_path, page_pdf_path=pdf_path, text="텍스트")
    _add_page_with_result(window, result)

    # 처리된 결과가 있으면 평소엔 활성화돼야 한다.
    window._refresh_crop_rotate_panel(image_path)
    assert window.crop_rotate_button.isEnabled() is True

    batch_thread = _start_blocking_thread(qtbot)
    try:
        window._worker = batch_thread
        window._refresh_crop_rotate_panel(image_path)
        assert window.crop_rotate_button.isEnabled() is False
        assert window._is_batch_processing() is True
    finally:
        _stop_blocking_thread(batch_thread)
        window._worker = None

    window._refresh_crop_rotate_panel(image_path)
    assert window.crop_rotate_button.isEnabled() is True


def test_crop_rotate_button_disabled_while_reprocessing(qtbot, tmp_path):
    """HIGH #1(연장): 재처리가 이미 실행 중이면(TOCTOU로 지연된 콜백이 재확인해도)
    버튼이 다시 켜지면 안 된다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "page.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    result = PageResult(input_path=image_path, page_pdf_path=pdf_path, text="텍스트")
    _add_page_with_result(window, result)

    reprocess_thread = _start_blocking_thread(qtbot)
    try:
        window._reprocess_worker = reprocess_thread
        window._refresh_crop_rotate_panel(image_path)
        assert window.crop_rotate_button.isEnabled() is False
        assert window._is_reprocessing() is True
    finally:
        _stop_blocking_thread(reprocess_thread)
        window._reprocess_worker = None

    window._refresh_crop_rotate_panel(image_path)
    assert window.crop_rotate_button.isEnabled() is True


def test_start_processing_blocked_when_vectorize_worker_running(qtbot, tmp_path, monkeypatch):
    """HIGH #2: 벡터화(또는 재처리) 워커가 실행 중이면 "처리 시작"이 새 배치를 만들면 안 된다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake-image-bytes")
    window._add_image_paths([image_path])

    warnings: list[str] = []
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[-1]),
    )

    vectorize_thread = _start_blocking_thread(qtbot)
    try:
        window._vectorize_worker = vectorize_thread
        window._start_processing()
        assert warnings, "다른 워커 실행 중에는 경고를 띄워야 한다."
        assert window._worker is None, "새 배치 워커가 시작되면 안 된다."
    finally:
        _stop_blocking_thread(vectorize_thread)
        window._vectorize_worker = None


def test_running_background_workers_aggregates_all_three(qtbot):
    """`_running_background_workers()`가 배치/벡터화/재처리 세 워커를 모두 확인하는지."""
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._running_background_workers() == []

    thread = _start_blocking_thread(qtbot)
    try:
        window._reprocess_worker = thread
        assert window._running_background_workers() == [thread]
    finally:
        _stop_blocking_thread(thread)
        window._reprocess_worker = None


def test_reprocess_finished_toctou_does_not_clobber_newer_worker_reference(qtbot, tmp_path):
    """MEDIUM #3: 예전(먼저 시작된) 재처리 워커의 지연된 `finished` 콜백이 뒤늦게 도착해도,
    이미 시작된 새 재처리 워커의 참조(`self._reprocess_worker`)를 지우면 안 된다."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "page.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    initial_result = PageResult(input_path=image_path, page_pdf_path=pdf_path, text="이전 텍스트")
    _add_page_with_result(window, initial_result)

    dummy_image = np.zeros((4, 4, 3), dtype=np.uint8)
    old_worker = ReprocessWorker(dummy_image, image_path, pdf_path)
    new_worker = ReprocessWorker(dummy_image, image_path, pdf_path)

    # 사용자가 같은 페이지의 재처리를 다시 시작해, self._reprocess_worker가 이미
    # new_worker를 가리키고 있는 상황을 흉내낸다.
    window._reprocess_worker = new_worker

    # old_worker(먼저 시작됐던 재처리)가 성공적으로 끝난 뒤 그 finished 콜백이
    # 이제야 GUI 스레드에서 처리되는 상황을 재현한다.
    stale_pdf_path = tmp_path / "stale_result.pdf"
    stale_pdf_path.write_bytes(b"%PDF-1.4 stale")
    old_worker.page_result = PageResult(
        input_path=image_path, page_pdf_path=stale_pdf_path, text="예전 재처리 결과"
    )

    window._on_reprocess_finished(old_worker, image_path, 0, None)

    # 예전 워커의 콜백이 새 워커의 참조를 지우면 안 된다.
    assert window._reprocess_worker is new_worker


def test_reprocess_error_toctou_does_not_clobber_newer_worker_reference(qtbot, tmp_path):
    """MEDIUM #3(오류 경로): `_on_reprocess_error`도 동일한 원칙을 지켜야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._work_dir = tmp_path

    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "page.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    initial_result = PageResult(input_path=image_path, page_pdf_path=pdf_path, text="이전 텍스트")
    _add_page_with_result(window, initial_result)

    dummy_image = np.zeros((4, 4, 3), dtype=np.uint8)
    old_worker = ReprocessWorker(dummy_image, image_path, pdf_path)
    new_worker = ReprocessWorker(dummy_image, image_path, pdf_path)
    window._reprocess_worker = new_worker

    window._on_reprocess_error(old_worker, "예전 재처리 실패", image_path)

    assert window._reprocess_worker is new_worker
