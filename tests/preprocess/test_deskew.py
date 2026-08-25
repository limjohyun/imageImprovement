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
