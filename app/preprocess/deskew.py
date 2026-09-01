"""PRE-2: 기울기 보정(deskew).

원근 보정(PRE-1) 후에도 남을 수 있는 미세한 회전을 Hough 변환으로 지배적인
직선의 각도를 추정해 보정한다. 원근 보정 없이 이 단계만 단독으로 써도 되도록
(예: 이미 정면에 가깝게 촬영된 이미지) 별도 모듈로 분리했다.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def estimate_skew_angle(image: np.ndarray, *, angle_limit: float = 15.0) -> float:
    """이미지에 남은 회전 각도(도)를 추정한다.

    반환값을 그대로 `cv2.getRotationMatrix2D`의 angle 인자로 넘기면 수평이 맞춰진다.
    직선을 충분히 찾지 못하면 0.0(보정 없음)을 반환한다 — 문서 윤곽선이 거의 없는
    이미지(예: 사진 위주 슬라이드)에서 억지로 회전시켜 오히려 왜곡을 더하지 않기 위함이다.

    1차 시도(threshold=100)에서 직선을 하나도 찾지 못하면(`lines is None`), 배경 없이
    프레임을 꽉 채운 촬영 구도 등으로 직선 신호가 약한 실제 사진에서 각도 추정이
    통째로 실패하는 문제가 있어 완화된 파라미터로 2차 시도를 한 번 더 한다. 2차 시도도
    실패하면(여전히 `lines is None`) 위와 같은 이유로 0.0을 반환한다.
    """
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # (threshold, 최소 길이 분모, 선분 간 최대 허용 간격) 쌍을 순서대로 시도한다.
    # 1차는 기존 파라미터 그대로이고, 2차는 threshold와 최소 길이 요구치를 각각
    # 절반으로 완화한 값이다 — 실제 문제 사진(IMG_2442/2443)과 합성 테스트를 함께
    # 스윕해 실측으로 정했다(자세한 근거는 작업 보고 참고).
    attempts = ((100, 4, 20), (50, 8, 20))
    lines = None
    for threshold, min_line_length_div, max_line_gap in attempts:
        min_line_length = max(20, gray.shape[1] // min_line_length_div)
        lines = cv2.HoughLinesP(
            edges,
            1,
            np.pi / 180,
            threshold=threshold,
            minLineLength=min_line_length,
            maxLineGap=max_line_gap,
        )
        if lines is not None:
            break

    if lines is None:
        return 0.0

    angles: list[float] = []
    for line in lines:
        x1, y1, x2, y2 = line.reshape(-1)
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        # 수평(0도)/수직(90도) 선이 섞여 검출되므로 -45~45도 범위로 정규화한다.
        if angle < -45:
            angle += 90
        elif angle > 45:
            angle -= 90
        if abs(angle) <= angle_limit:
            angles.append(angle)

    if not angles:
        return 0.0
    return float(np.median(angles))


def deskew(image: np.ndarray, *, angle: float | None = None) -> np.ndarray:
    """PRE-2 진입점. `angle`을 생략하면 `estimate_skew_angle`로 자동 추정해 보정한다."""
    if angle is None:
        angle = estimate_skew_angle(image)
    if abs(angle) < 0.1:
        return image

    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    border_value = (255, 255, 255) if image.ndim == 3 else 255
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )
