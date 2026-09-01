"""PRE-3: 조명/그림자 보정.

큰 커널의 가우시안 블러로 배경 조도 맵을 추정한 뒤 원본을 그 맵으로 나누는
division normalization 방식을 쓴다. 색상(A/B 채널)은 건드리지 않고 LAB의
L(밝기) 채널에만 적용해, 조명만 균일화하고 색조는 보존한다.

비율(`channel / background`)을 0~255로 매핑할 때는 적응형 min-max 정규화를 쓰지
않는다. 실사진에서는 하이라이트나 배경 추정 오차로 생기는 극소수 이상치 픽셀 때문에
비율의 최댓값이 실제 배경(비율 ~1.0)보다 훨씬 크게 튀는 경우가 흔한데, min-max
정규화는 이 이상치를 기준으로 전체 범위를 늘려버려 정상 배경이 어두운 값으로
짓눌리는 문제가 있었다(실측: 평균 밝기 157.6 → 48.4로 급락). 대신 비율 1.0(배경이
자기 자신과 같음)을 흰색(255) 근처로 고정 앵커링하는 고정 스케일(`ratio * 255`,
클리핑)을 쓴다. 텍스트/악보처럼 어두운 전경 객체가 있는 문서는 배경이 거의 흰색에
가깝게, 전경은 그대로 어둡게 유지되어 흑백 대비가 뚜렷해진다.

입력 이미지는 BGR uint8을 가정한다(`cv2.COLOR_BGR2LAB` 변환 기준). RGB 배열을
그대로 넘기면 색조가 어긋난 채로 LAB 변환된다.
"""

from __future__ import annotations

import cv2
import numpy as np


def _normalize_channel(channel: np.ndarray, kernel_fraction: float) -> np.ndarray:
    """단일 채널에 division normalization을 적용해 배경 밝기를 균일화한다."""
    height, width = channel.shape[:2]
    kernel_size = max(3, int(min(height, width) * kernel_fraction))
    if kernel_size % 2 == 0:
        kernel_size += 1
    channel_f = channel.astype(np.float32)
    background = cv2.GaussianBlur(channel_f, (kernel_size, kernel_size), 0)
    normalized = channel_f / (background + 1e-6)
    # 비율 1.0(정상 배경)을 흰색(255) 근처로 고정 앵커링한다. 적응형 min-max는
    # 소수의 이상치 픽셀에 전체 범위가 끌려가 배경 전체가 어두워지는 문제가 있었다.
    return np.clip(normalized * 255.0, 0, 255).astype(np.uint8)


def correct_illumination(image: np.ndarray, *, kernel_fraction: float = 0.15) -> np.ndarray:
    """PRE-3 진입점: 불균일 조명/그림자를 완화해 배경을 균일화한다.

    `kernel_fraction`은 배경 조도 맵 추정에 쓰는 블러 커널 크기를 이미지 짧은 변에
    대한 비율로 지정한다(기본 0.15) — 문서 안의 글자/도형 같은 세부 구조는 지우고
    조명 변화만 남기려면 커널이 충분히 커야 한다.
    """
    if image.ndim == 2:
        return _normalize_channel(image, kernel_fraction)

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, a_channel, b_channel = cv2.split(lab)
    corrected_lightness = _normalize_channel(lightness, kernel_fraction)
    corrected_lab = cv2.merge([corrected_lightness, a_channel, b_channel])
    return cv2.cvtColor(corrected_lab, cv2.COLOR_LAB2BGR)
