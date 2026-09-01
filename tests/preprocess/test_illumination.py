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


def test_correct_illumination_is_robust_to_local_highlight_outlier():
    """국소 이상치(작은 하이라이트) 때문에 배경 전체가 어두워지던 회귀를 방지한다.

    실제 사진에서 어두운 전경(텍스트/음표) 내부에 작은 반사광 같은 극단적으로 밝은
    이상치 픽셀이 섞이면, 적응형 min-max 정규화는 그 이상치를 기준으로 전체 범위를
    늘려버려 정상 배경(균일한 밝기)까지 크게 어두워지는 문제가 있었다. 고정 스케일
    (`ratio * 255`, 클리핑) 방식은 이런 이상치에 영향받지 않고 배경을 밝게 유지해야 한다.
    """
    height, width = 400, 400
    image = np.full((height, width, 3), 160, dtype=np.uint8)
    image[180:220, 80:320] = 20  # 어두운 전경(텍스트) 영역
    image[195:199, 195:199] = 255  # 전경 내부의 초소형 밝은 이상치(반사광 등)

    corrected = correct_illumination(image)
    corrected_gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)

    background_mask = np.ones((height, width), dtype=bool)
    background_mask[180:220, 80:320] = False
    background_mean = float(corrected_gray[background_mask].mean())

    # 원본 배경(160)보다 어두워지기는커녕 흰색에 가깝게 유지되어야 한다.
    assert background_mean > 200.0
