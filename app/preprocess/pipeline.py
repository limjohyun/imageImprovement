"""PRE-5: 공통 전처리 파이프라인 조합.

PRE-1~4(원근보정 → deskew → 조명보정 → 업스케일)를 순서대로 엮어, `processors/*`가
이미지 한 장을 넣으면 전처리된 결과를 바로 받을 수 있게 한다. 각 단계는
`perspective.py`/`deskew.py`/`illumination.py`/`upscale.py`에 독립 함수로도
공개돼 있으므로, 문서 유형별로 순서를 바꾸거나 일부 단계를 건너뛰어야 하는 경우
(예: 이미 정면으로 스캔된 이미지)는 개별 함수를 직접 조합해도 된다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.preprocess.deskew import deskew
from app.preprocess.illumination import correct_illumination
from app.preprocess.perspective import DocumentCornersNotFoundError, correct_perspective
from app.preprocess.upscale import upscale

logger = logging.getLogger(__name__)


@dataclass
class PreprocessConfig:
    """`run_pipeline()`의 단계별 on/off 및 파라미터."""

    corners: np.ndarray | None = None
    """PRE-1 수동 좌표(GUI에서 사용자가 4점을 지정한 경우). None이면 자동 검출을 시도한다."""

    skip_perspective_on_failure: bool = True
    """자동 검출 실패 시 예외를 던지는 대신 원근 보정 단계만 건너뛰고 계속 진행할지 여부.

    기본값을 True로 둔 이유: GUI 없이 여러 장을 배치 처리할 때 한 장의 검출 실패가
    전체 파이프라인을 멈추게 하지 않기 위함이다. 수동 4점 지정 UX를 제공하려는
    호출자(GUI)는 False로 두고 `DocumentCornersNotFoundError`를 직접 잡아
    사용자 입력을 받은 뒤 `corners`를 채워 재시도하면 된다.
    """

    deskew_angle: float | None = None
    illumination_kernel_fraction: float = 0.15
    upscale_scale: float = 2.0
    upscale_model_path: str | Path | None = None

    run_perspective: bool = True
    run_deskew: bool = True
    run_illumination: bool = True
    run_upscale: bool = True


def run_pipeline(image: np.ndarray, config: PreprocessConfig | None = None) -> np.ndarray:
    """PRE-1~4를 순서대로 적용한 전처리 결과 이미지를 반환한다 (PRE-5)."""
    config = config or PreprocessConfig()
    result = image

    if config.run_perspective:
        try:
            result = correct_perspective(result, corners=config.corners)
        except DocumentCornersNotFoundError:
            if not config.skip_perspective_on_failure:
                raise
            logger.info("원근 보정을 건너뜁니다(문서 윤곽 자동 검출 실패).")

    if config.run_deskew:
        result = deskew(result, angle=config.deskew_angle)

    if config.run_illumination:
        result = correct_illumination(result, kernel_fraction=config.illumination_kernel_fraction)

    if config.run_upscale:
        result = upscale(result, scale=config.upscale_scale, model_path=config.upscale_model_path)

    return result
