"""Phase5-1(BKP-1) 수용 기준 검증: 로컬 저장 우선 보장 + 백업 설정 UI.

`MainWindow`가 생성하는 기본 `BackupSettings()`는 실사용 시 시스템 표준 위치(네이티브
`QSettings`)에 영속화되므로, 테스트가 개발자의 실제 프리퍼런스 파일을 건드리지
않도록 `app.gui.main_window.BackupSettings`를 `tmp_path` 아래 격리된 `.ini` 파일을
가리키는 인스턴스로 monkeypatch하거나, 생성 이후 `window._backup_settings`를
직접 교체해 사용한다.
"""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QSettings

from app.backup.settings import BackupSettings
from app.gui.main_window import MainWindow


def _ini_settings(path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def _write_minimal_pdf(path) -> None:
    doc = pymupdf.open()
    doc.new_page(width=200, height=200)
    doc.save(path)
    doc.close()


def test_backup_checkbox_defaults_to_off(qtbot, tmp_path, monkeypatch):
    """(a) 백업 설정 기본값은 반드시 off여야 한다 — 체크박스도 이를 그대로 반영한다."""
    monkeypatch.setattr(
        "app.gui.main_window.BackupSettings",
        lambda: BackupSettings(_ini_settings(tmp_path / "backup.ini")),
    )

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.backup_enabled_checkbox.isChecked() is False
    assert window._backup_settings.is_backup_enabled() is False


def test_backup_checkbox_toggle_persists(qtbot, tmp_path, monkeypatch):
    """(b) 체크박스 토글이 설정 저장소에 저장되고, 새 인스턴스에서도 복원된다."""
    ini_path = tmp_path / "backup.ini"
    monkeypatch.setattr(
        "app.gui.main_window.BackupSettings",
        lambda: BackupSettings(_ini_settings(ini_path)),
    )

    window = MainWindow()
    qtbot.addWidget(window)

    window.backup_enabled_checkbox.setChecked(True)
    assert BackupSettings(_ini_settings(ini_path)).is_backup_enabled() is True

    window.backup_enabled_checkbox.setChecked(False)
    assert BackupSettings(_ini_settings(ini_path)).is_backup_enabled() is False


def test_save_does_not_trigger_upload_when_backup_disabled(qtbot, tmp_path, monkeypatch):
    """(c) 백업이 꺼져 있으면 저장 흐름이 업로드 훅을 아예 호출하지 않는다(오프라인 보장)."""
    upload_calls = []
    monkeypatch.setattr(
        "app.gui.main_window.upload_pdf",
        lambda *args, **kwargs: upload_calls.append((args, kwargs)),
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window._backup_settings = BackupSettings(_ini_settings(tmp_path / "backup.ini"))
    assert window._backup_settings.is_backup_enabled() is False

    source_pdf = tmp_path / "merged.pdf"
    _write_minimal_pdf(source_pdf)
    window._merged_pdf_path = source_pdf

    destination = tmp_path / "out.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )

    window._on_save_clicked()

    assert destination.exists()
    assert upload_calls == []


def test_save_succeeds_even_if_backup_hook_raises(qtbot, tmp_path, monkeypatch):
    """(d) 백업 훅이 예외를 던져도 `_on_save_clicked()`의 로컬 저장 성공에는 영향이 없다."""

    def _boom(*args, **kwargs):
        raise RuntimeError("네트워크에 연결할 수 없습니다 (테스트용 모킹)")

    monkeypatch.setattr("app.gui.main_window.upload_pdf", _boom)

    window = MainWindow()
    qtbot.addWidget(window)
    window._backup_settings = BackupSettings(_ini_settings(tmp_path / "backup.ini"))
    window._backup_settings.set_backup_enabled(True)

    source_pdf = tmp_path / "merged.pdf"
    _write_minimal_pdf(source_pdf)
    window._merged_pdf_path = source_pdf

    destination = tmp_path / "out.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )

    # 백업 훅에서 예외가 나도 여기서 예외가 전파되면 안 된다(BKP-1 핵심 계약).
    window._on_save_clicked()

    assert destination.exists()
    with pymupdf.open(destination) as doc:
        assert doc.page_count == 1
