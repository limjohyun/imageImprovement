"""BKP-1~4: 선택적 클라우드 백업 (docs/prd.md §5.8).

기본 워크플로우는 항상 로컬 완결이며, 이 패키지는 사용자가 설정에서 명시적으로
켰을 때만 관여하는 부가 기능이다. 공개 API는 이 패키지 최상위에서 바로
import할 수 있게 노출한다:

    from app.backup import BackupSettings, upload_pdf

Phase5-1(BKP-1)은 `BackupSettings`(활성화 여부 저장/조회, 기본값 False)와
`upload_pdf`(다음 태스크가 채울 no-op 스텁)만 제공한다. 실제 Supabase 업로드
(BKP-2)와 자격증명 관리(BKP-4)는 이어지는 Phase5 태스크의 몫이다.
"""

from __future__ import annotations

from app.backup.settings import BackupSettings
from app.backup.uploader import upload_pdf

__all__ = ["BackupSettings", "upload_pdf"]
