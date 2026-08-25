"""문서 유형과 무관한 공통 전처리 모듈 (PRE-1~5).

`app/processors/*`는 이 패키지의 함수를 그대로 재사용해야 하며, 문서 유형별로
원근보정/deskew/조명보정/업스케일을 중복 구현하지 않는다.
"""

from __future__ import annotations

from app.preprocess.deskew import deskew, estimate_skew_angle
from app.preprocess.illumination import correct_illumination
from app.preprocess.perspective import (
    DocumentCornersNotFoundError,
    correct_perspective,
    detect_document_corners,
    warp_to_corners,
)
from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.preprocess.upscale import upscale, upscale_classical, upscale_real_esrgan

__all__ = [
    "DocumentCornersNotFoundError",
    "PreprocessConfig",
    "correct_illumination",
    "correct_perspective",
    "deskew",
    "detect_document_corners",
    "estimate_skew_angle",
    "run_pipeline",
    "upscale",
    "upscale_classical",
    "upscale_real_esrgan",
    "warp_to_corners",
]
