"""Phase3-4(SCR-3 UI) 수용 기준 검증: `MainWindow`의 악보 처리 경로 UI 반응.

`ProcessingWorker`의 실제 라우팅/분류 로직은 `tests/gui/test_worker_routing.py`,
`tests/router/test_dispatch.py`에서 이미 검증하므로, 여기서는 이미 채워진
`PageResult`를 직접 주입해 `MainWindow`가 SCORE 문서 유형에 따라 화면을 올바르게
반응시키는지(텍스트 검수 패널의 전용 안내 문구, "MuseScore에서 열기" 버튼 활성화 조건,
클릭 시 `open_score_in_external_editor` 호출 및 반환된 `Popen` 참조 보관)를 스모크
수준으로 확인한다.

이 개발 머신엔 oemer 체크포인트가 없어 실제 악보 사진을 처리해 성공하는 흐름은
검증할 수 없으므로(`ProcessingWorker`가 항상 `ScoreModelUnavailableError`를 낼 것),
여기서는 이미 성공적으로 처리된 것처럼 `PageResult`를 직접 구성해 순수 UI 반응만 본다.
"""

from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt

from app.gui.main_window import MainWindow
from app.gui.worker import PageResult
from app.processors.score import ScoreRendererUnavailableError
from app.router.classifier import DocumentType


def _add_page_with_result(window: MainWindow, result: PageResult) -> None:
    window._add_image_paths([result.input_path])
    window._results_by_input[str(result.input_path.resolve())] = result


def test_score_page_shows_dedicated_message_instead_of_unprocessed(qtbot, tmp_path):
    """SCR-3: 악보 페이지는 '아직 처리되지 않았습니다'가 아니라 전용 안내 문구를 보여준다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "score.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "score.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    musicxml_path = tmp_path / "score.musicxml"
    musicxml_path.write_text("<score-partwise/>")
    result = PageResult(
        input_path=image_path,
        page_pdf_path=pdf_path,
        text=None,
        document_type=DocumentType.SCORE,
        musicxml_path=musicxml_path,
    )
    _add_page_with_result(window, result)

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    assert window.text_review_edit.isEnabled() is False
    assert (
        window.text_review_edit.placeholderText()
        == "이 페이지는 악보로 분류되어 텍스트 검수 대상이 아닙니다."
    )
    assert window.open_in_musescore_button.isEnabled() is True


def test_open_in_musescore_button_disabled_for_text_and_diagram_pages(qtbot, tmp_path):
    """텍스트/도형 페이지에서는 "MuseScore에서 열기" 버튼이 비활성화되어야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)

    text_path = tmp_path / "text.png"
    text_path.write_bytes(b"fake-image-bytes")
    text_pdf = tmp_path / "text.pdf"
    text_pdf.write_bytes(b"%PDF-1.4 fake")
    text_result = PageResult(
        input_path=text_path,
        page_pdf_path=text_pdf,
        text="인식된 텍스트",
        document_type=DocumentType.TEXT,
    )
    _add_page_with_result(window, text_result)

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert window.open_in_musescore_button.isEnabled() is False


def test_open_in_musescore_button_disabled_when_musicxml_missing(qtbot, tmp_path):
    """SCORE로 분류됐더라도 `musicxml_path`가 아직 없으면(예: 처리 실패) 버튼은 비활성화된다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "score.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "score.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    result = PageResult(
        input_path=image_path,
        page_pdf_path=pdf_path,
        text=None,
        document_type=DocumentType.SCORE,
        musicxml_path=None,
    )
    _add_page_with_result(window, result)

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert window.open_in_musescore_button.isEnabled() is False


def test_open_in_musescore_button_click_calls_editor_with_correct_path_and_keeps_reference(
    qtbot, tmp_path, monkeypatch
):
    """SCR-3: 버튼 클릭 시 `open_score_in_external_editor`가 올바른 MusicXML 경로로
    호출되고, 반환된 `Popen`이 `MainWindow` 인스턴스에 계속 참조로 남아야 한다
    (참조를 놓으면 실행 중인 프로세스가 GC되며 ResourceWarning이 날 수 있다,
    code-reviewer 지적 사항)."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "score.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "score.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    musicxml_path = tmp_path / "score.musicxml"
    musicxml_path.write_text("<score-partwise/>")
    result = PageResult(
        input_path=image_path,
        page_pdf_path=pdf_path,
        text=None,
        document_type=DocumentType.SCORE,
        musicxml_path=musicxml_path,
    )
    _add_page_with_result(window, result)
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    calls: list[object] = []
    fake_process = subprocess.Popen(["true"])
    fake_process.wait()  # 실제 MuseScore를 띄우지 않고, 이미 끝난 더미 프로세스만 반환한다.

    def fake_open_score_in_external_editor(path, **kwargs):
        calls.append(path)
        return fake_process

    monkeypatch.setattr(
        "app.gui.main_window.open_score_in_external_editor",
        fake_open_score_in_external_editor,
    )

    qtbot.mouseClick(window.open_in_musescore_button, Qt.MouseButton.LeftButton)

    assert calls == [musicxml_path]
    assert fake_process in window._open_musescore_processes


def test_open_in_musescore_button_click_shows_error_when_musescore_unavailable(
    qtbot, tmp_path, monkeypatch
):
    """SCR-3: MuseScore 실행 파일을 찾지 못하면 `QMessageBox.critical`로 사용자에게 알려야 한다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "score.png"
    image_path.write_bytes(b"fake-image-bytes")
    pdf_path = tmp_path / "score.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    musicxml_path = tmp_path / "score.musicxml"
    musicxml_path.write_text("<score-partwise/>")
    result = PageResult(
        input_path=image_path,
        page_pdf_path=pdf_path,
        text=None,
        document_type=DocumentType.SCORE,
        musicxml_path=musicxml_path,
    )
    _add_page_with_result(window, result)
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))

    def fake_raise(path, **kwargs):
        raise ScoreRendererUnavailableError("MuseScore 실행 파일을 찾을 수 없습니다.")

    monkeypatch.setattr("app.gui.main_window.open_score_in_external_editor", fake_raise)

    shown_messages: list[str] = []
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.critical",
        lambda *args, **kwargs: shown_messages.append(args[-1]),
    )

    qtbot.mouseClick(window.open_in_musescore_button, Qt.MouseButton.LeftButton)

    assert shown_messages
    assert window._open_musescore_processes == []
