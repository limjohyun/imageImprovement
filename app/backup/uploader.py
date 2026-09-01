"""Phase5-1(BKP-1) 스텁: 백업 업로드 지점을 위한 얇은 인터페이스.

실제 Supabase 클라이언트 연동/네트워크 호출(BKP-2)은 Phase5-2의 몫이다.
지금은 "로컬 저장이 항상 먼저 끝난 뒤에만 호출되는 지점"이라는 계약만 세워두고,
호출돼도 아무 일도 하지 않는 no-op으로 둔다.

호출자(`app/gui/main_window.py`의 저장 흐름 훅)는 이 함수가 예외를 던지지
않고 즉시 반환한다고 가정할 수 있어야 한다 — BKP-1("백업 실패가 로컬 저장
결과에 영향을 주지 않는다")과 BKP-3(오프라인 동작 보장)의 핵심 계약이다.
Phase5-2가 실제 네트워크 호출을 채워 넣을 때도 이 함수 내부에서 예외를 삼키는
것에 의존하지 말고, 호출부(`_attempt_backup`)가 여전히 try/except로 감싸는
이중 방어 구조를 유지해야 한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def upload_pdf(pdf_path: Path, *, document_type: str | None = None) -> None:
    """완성된 PDF를 백업 대상(Supabase Storage 등)에 업로드한다.

    Phase5-2(BKP-2)가 실제 Supabase Storage 업로드 + Postgres 메타데이터 기록으로
    채울 자리. 지금은 로그만 남기고 반환하는 no-op이다.
    """
    logger.info(
        "백업이 켜져 있지만 업로드 구현은 아직 없습니다(Phase5-2에서 구현 예정): "
        "pdf_path=%s, document_type=%s",
        pdf_path,
        document_type,
    )
