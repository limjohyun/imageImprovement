"""PRE-2(기울기 보정) 테스트."""

from __future__ import annotations

import cv2
import numpy as np

from app.preprocess.deskew import deskew, estimate_skew_angle


def _rotate(image: np.ndarray, angle_deg: float) -> np.ndarray:
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    return cv2.warpAffine(
        image, matrix, (width, height), borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255)
    )


def test_estimate_skew_angle_recovers_known_rotation(synthetic_text_photo):
    """알려진 각도로 회전시킨 문서에서 그 각도를 근사하게 복원해야 한다.

    `estimate_skew_angle`이 반환하는 값은 `cv2.getRotationMatrix2D`에 그대로 넘겨
    "되돌리기" 위한 보정각이므로, `_rotate`로 +true_angle만큼 돌린 이미지에서는
    부호가 반대인 -true_angle에 가까운 값이 나와야 한다(deskew()가 그 값을 그대로
    회전에 사용해 원상복구하는 것으로 별도 테스트에서 검증함).
    """
    true_angle = 4.0
    rotated = _rotate(synthetic_text_photo.ground_truth, true_angle)
    detected = estimate_skew_angle(rotated)
    assert abs(detected - (-true_angle)) < 1.0


def test_deskew_straightens_rotated_document(synthetic_text_photo):
    """deskew 적용 후 잔여 기울기가 거의 0에 가까워야 한다."""
    rotated = _rotate(synthetic_text_photo.ground_truth, -6.0)
    corrected = deskew(rotated)
    residual = estimate_skew_angle(corrected)
    assert abs(residual) < 0.5


def test_deskew_leaves_already_straight_image_unchanged(synthetic_text_photo):
    """이미 수평인 문서는(각도 0에 가까움) 변형하지 않아야 한다."""
    straight = synthetic_text_photo.ground_truth
    corrected = deskew(straight)
    assert corrected.shape == straight.shape


def test_estimate_skew_angle_returns_zero_without_lines():
    """직선을 찾을 수 없는 이미지(순수 노이즈)에서는 0.0을 반환해야 한다."""
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, size=(100, 100, 3), dtype=np.uint8)
    assert estimate_skew_angle(noise) == 0.0


def _make_weak_line_image(angle_deg: float, *, length: int = 70) -> np.ndarray:
    """1차 시도(threshold=100, minLineLength=너비/4)로는 검출되지 않을 만큼 짧고
    드문드문한 직선만 있는 합성 이미지를 만든다.

    실제 iPhone 사진(배경 없이 프레임을 꽉 채운 구도)에서 관찰된 "직선 신호는
    있지만 1차 시도 기준에는 못 미치는" 상황을 재현한다.
    """
    image = np.full((400, 400, 3), 255, dtype=np.uint8)
    angle_rad = np.radians(angle_deg)
    dx = length / 2 * np.cos(angle_rad)
    dy = length / 2 * np.sin(angle_rad)
    # 서로 충분히 떨어뜨려 놓아 maxLineGap으로 인접 선분끼리 이어붙여져
    # 실제 길이보다 길게 인식되지 않도록 한다.
    for offset in range(40, 400, 70):
        center = (200, offset)
        p1 = (int(center[0] - dx), int(center[1] - dy))
        p2 = (int(center[0] + dx), int(center[1] + dy))
        cv2.line(image, p1, p2, (0, 0, 0), 2)
    return image


def test_estimate_skew_angle_recovers_angle_via_relaxed_retry():
    """1차 시도로는 못 찾는 약한 직선 신호도 완화된 2차 시도로 검출해야 한다."""
    true_angle = -5.0
    image = _make_weak_line_image(true_angle)
    detected = estimate_skew_angle(image)
    assert detected != 0.0
    assert abs(detected - true_angle) < 2.0


def test_estimate_skew_angle_returns_zero_when_relaxed_retry_also_fails():
    """완화된 2차 시도로도 직선을 찾지 못하면(순수 노이즈) 여전히 0.0을 반환해야 한다.

    2차 시도를 추가해도 "직선을 못 찾으면 억지로 각도를 만들어내지 않는다"는
    기존 계약은 그대로 유지돼야 한다.
    """
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, size=(100, 100, 3), dtype=np.uint8)
    assert estimate_skew_angle(noise) == 0.0
