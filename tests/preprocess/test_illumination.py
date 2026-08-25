"""PRE-3(조명/그림자 보정) 테스트."""

from __future__ import annotations

import cv2
import numpy as np

from app.preprocess.illumination import correct_illumination


def _block_brightness_std(gray: np.ndarray, blocks: int = 4) -> float:
    """이미지를 blocks x blocks 격자로 나눈 뒤 각 블록 평균 밝기의 표준편차를 구한다.

    값이 작을수록 배경 밝기가 균일하다는 뜻이므로 조명 보정 효과를 측정하는 지표로 쓴다.
    """
    height, width = gray.shape[:2]
    means = []
    step_h, step_w = height // blocks, width // blocks
    for row in range(blocks):
        for col in range(blocks):
            block = gray[row * step_h : (row + 1) * step_h, col * step_w : (col + 1) * step_w]
            means.append(block.mean())
    return float(np.std(means))


def test_correct_illumination_reduces_brightness_variance(synthetic_text_photo):
    """조명 그라디언트가 적용된 촬영본의 배경 밝기 불균일도가 보정 후 줄어들어야 한다."""
    before = cv2.cvtColor(synthetic_text_photo.photo, cv2.COLOR_BGR2GRAY)
    corrected = correct_illumination(synthetic_text_photo.photo)
    after = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)

    std_before = _block_brightness_std(before)
    std_after = _block_brightness_std(after)
    assert std_after < std_before * 0.5


def test_correct_illumination_preserves_shape_and_dtype(synthetic_diagram_photo):
    corrected = correct_illumination(synthetic_diagram_photo.photo)
    assert corrected.shape == synthetic_diagram_photo.photo.shape
    assert corrected.dtype == np.uint8


def test_correct_illumination_handles_grayscale_input():
    gray = np.full((80, 80), 200, dtype=np.uint8)
    gray[:, :40] = 100  # 좌우 밝기 차이를 인위적으로 만든다
    corrected = correct_illumination(gray)
    assert corrected.shape == gray.shape
    assert corrected.dtype == np.uint8
