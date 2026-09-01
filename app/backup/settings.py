"""Phase5-1(BKP-1): 백업 활성화 여부를 저장/조회하는 최소 설정 모듈.

`QSettings`(Qt 표준 영속 저장소, PySide6에 이미 포함돼 있어 새 의존성이 필요
없다)를 사용한다. 기본값은 반드시 `False`(꺼짐)여야 한다 — §2/§8의 오프라인
목표 및 BKP-3(오프라인 동작 보장)과 상충하지 않도록, 사용자가 명시적으로 켜지
않는 한 백업은 항상 비활성 상태다.

이 모듈은 "켜고 끄는 스위치"의 영속화만 다룬다. Supabase URL/API 키 등
자격증명 관리(BKP-4)는 다음 태스크(Phase5-3)의 몫이다.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

# 개인용 로컬 도구이므로 조직/앱 이름은 QSettings가 macOS에서 설정 파일 경로를
# 결정하는 데만 쓰인다(예: ~/Library/Preferences/com.imageimprovement.ImageImprovementTool.plist).
_ORGANIZATION = "ImageImprovement"
_APPLICATION = "ImageImprovementTool"
_BACKUP_ENABLED_KEY = "backup/enabled"


class BackupSettings:
    """백업 활성화 여부(BKP-1)의 저장/조회를 담당하는 얇은 래퍼.

    `qsettings`를 생성자에서 주입할 수 있게 해, 테스트가 실제 사용자 프리퍼런스
    파일을 건드리지 않고 임시 `QSettings(QSettings.Format.IniFormat, ...)`로
    격리해 검증할 수 있게 한다. 인자를 생략하면(GUI 실사용 경로) 시스템 표준
    위치에 영속화되는 네이티브 `QSettings`를 사용한다.
    """

    def __init__(self, qsettings: QSettings | None = None) -> None:
        self._settings = (
            qsettings if qsettings is not None else QSettings(_ORGANIZATION, _APPLICATION)
        )

    def is_backup_enabled(self) -> bool:
        """백업 활성화 여부를 반환한다. 저장된 값이 없으면 기본값 `False`."""
        # QSettings는 값을 문자열로 저장하는 백엔드(IniFormat 등)가 있어
        # `type=bool`을 명시하지 않으면 "false" 문자열이 파이썬에서 truthy로
        # 잘못 해석될 수 있다.
        return bool(self._settings.value(_BACKUP_ENABLED_KEY, False, type=bool))

    def set_backup_enabled(self, enabled: bool) -> None:
        """백업 활성화 여부를 저장한다."""
        self._settings.setValue(_BACKUP_ENABLED_KEY, bool(enabled))
        self._settings.sync()
