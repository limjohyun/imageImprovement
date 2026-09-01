"""Phase5-1(BKP-1) 회귀 테스트: 백업 활성화 설정의 기본값/저장·복원.

실제 사용자 프리퍼런스 파일(네이티브 `QSettings`)을 건드리지 않도록, 매 테스트가
`tmp_path` 아래 격리된 `.ini` 파일을 가리키는 `QSettings(IniFormat)`을 직접 만들어
`BackupSettings`에 주입한다.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from app.backup.settings import BackupSettings


def _ini_settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_default_is_disabled(tmp_path):
    """(a) 저장된 값이 없으면 기본값은 반드시 False(꺼짐)여야 한다."""
    settings = BackupSettings(_ini_settings(tmp_path / "backup.ini"))

    assert settings.is_backup_enabled() is False


def test_toggle_persists_across_instances(tmp_path):
    """(b) 설정 토글이 같은 저장소를 가리키는 다른 인스턴스에서도 복원된다."""
    ini_path = tmp_path / "backup.ini"

    BackupSettings(_ini_settings(ini_path)).set_backup_enabled(True)
    assert BackupSettings(_ini_settings(ini_path)).is_backup_enabled() is True

    BackupSettings(_ini_settings(ini_path)).set_backup_enabled(False)
    assert BackupSettings(_ini_settings(ini_path)).is_backup_enabled() is False


def test_is_backup_enabled_returns_actual_bool_type(tmp_path):
    """IniFormat은 값을 문자열로 직렬화하므로, "false" 문자열이 파이썬에서
    truthy로 잘못 해석되지 않는지(`type=bool` 캐스팅) 확인한다."""
    ini_path = tmp_path / "backup.ini"
    BackupSettings(_ini_settings(ini_path)).set_backup_enabled(False)

    result = BackupSettings(_ini_settings(ini_path)).is_backup_enabled()

    assert result is False
