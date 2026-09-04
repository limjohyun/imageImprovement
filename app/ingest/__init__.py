"""이미지 입력 로딩/정규화 (docs/prd.md 아키텍처, "load & normalize input images").

공개 API는 이 패키지 최상위에서 바로 import할 수 있게 노출한다:

    from app.ingest import load_image_bgr
"""

from __future__ import annotations

from app.ingest.loader import load_image_bgr

__all__ = ["load_image_bgr"]
