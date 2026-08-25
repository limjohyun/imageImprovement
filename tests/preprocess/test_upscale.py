"""PRE-4(해상도 개선/디노이즈) 테스트.

Real-ESRGAN 경로는 사전학습 가중치(.pth) 파일이 로컬에 있어야 동작하는데, 이
저장소는 오프라인 기본 동작 원칙상 가중치를 자동으로 내려받지 않는다. 따라서
`upscale_real_esrgan`은 가중치가 실제로 존재할 때만 실행되는 `slow` 마커 테스트로
분리하고, 기본 스위트(`pytest -q`)는 가중치 없이도 항상 통과하는 클래식 폴백
경로만 검증한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.preprocess.upscale import upscale, upscale_classical, upscale_real_esrgan

# 사용자가 수동으로 가중치를 내려받아 두고 싶을 때를 위한 환경변수 기반 경로.
# 기본값은 비어 있으므로(가중치 미다운로드) 아래 slow 테스트는 항상 skip된다.
_REAL_ESRGAN_WEIGHTS = os.environ.get("REAL_ESRGAN_WEIGHTS_PATH", "")


def test_upscale_classical_scales_dimensions():
    small = np.full((40, 30, 3), 200, dtype=np.uint8)
    cv2.rectangle(small, (5, 5), (25, 20), (0, 0, 0), 1)
    result = upscale_classical(small, scale=2.0)
    assert result.shape[:2] == (80, 60)
    assert result.dtype == np.uint8


def test_upscale_classical_handles_grayscale():
    small = np.full((40, 30), 200, dtype=np.uint8)
    result = upscale_classical(small, scale=1.5)
    assert result.shape[:2] == (60, 45)


def test_upscale_falls_back_to_classical_when_model_path_missing(tmp_path: Path):
    """존재하지 않는 model_path를 넘겨도 예외 없이 클래식 폴백으로 계속 동작해야 한다."""
    small = np.full((40, 30, 3), 200, dtype=np.uint8)
    missing_path = tmp_path / "does_not_exist.pth"
    result = upscale(small, scale=2.0, model_path=missing_path)
    assert result.shape[:2] == (80, 60)


def test_upscale_default_entry_point_matches_classical():
    small = np.full((20, 20, 3), 128, dtype=np.uint8)
    assert upscale(small, scale=2.0).shape[:2] == upscale_classical(small, scale=2.0).shape[:2]


@pytest.mark.slow
@pytest.mark.skipif(
    not _REAL_ESRGAN_WEIGHTS or not Path(_REAL_ESRGAN_WEIGHTS).exists(),
    reason="REAL_ESRGAN_WEIGHTS_PATH 환경변수로 로컬 .pth 가중치 경로를 지정해야 실행된다.",
)
def test_upscale_real_esrgan_runs_on_tiny_image():
    """가중치가 준비된 환경에서만 CPU 추론 1회를 스모크 테스트한다(작은 이미지로 제한)."""
    tiny = np.full((32, 32, 3), 128, dtype=np.uint8)
    result = upscale_real_esrgan(tiny, model_path=_REAL_ESRGAN_WEIGHTS, scale=4)
    assert result.shape[0] >= tiny.shape[0] * 2
