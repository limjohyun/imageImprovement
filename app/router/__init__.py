"""RT-1, RT-2: 문서 유형 분류 + 처리기 라우팅 (docs/prd.md §5.2).

공개 API는 이 패키지 최상위에서 바로 import할 수 있게 노출한다:

    from app.router import DocumentType, classify_document_type, route_and_process
"""

from __future__ import annotations

from app.router.classifier import DocumentType, classify_document_type
from app.router.dispatch import UnsupportedDocumentTypeError, route_and_process

__all__ = [
    "DocumentType",
    "classify_document_type",
    "route_and_process",
    "UnsupportedDocumentTypeError",
]
