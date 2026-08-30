"""Phase4-1(GUI-3 일부) 수용 기준 검증: 자르기/회전 순수 이미지 변환.

Qt에 의존하지 않는 순수 함수라 일반 pytest로 검증한다.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.preprocess.manual_correction import apply_manual_correction, crop_image, rotate_image


def _make_gradient_image(width: int, height: int) -> np.ndarray:
    """픽셀 위치를 알아볼 수 있는 그라디언트 이미지를 만든다(회전/자르기 검증용)."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            image[y, x] = (x % 256, y % 256, 0)
    return image


def test_rotate_image_0_degrees_is_noop():
    image = _make_gradient_image(30, 20)
    rotated = rotate_image(image, 0)
    assert np.array_equal(rotated, image)


def test_rotate_image_90_degrees_swaps_dimensions():
    image = _make_gradient_image(30, 20)  # width=30, height=20
    rotated = rotate_image(image, 90)
    assert rotated.shape[:2] == (30, 20)  # (height, width) 반전


def test_rotate_image_180_degrees_flips_corner_pixels():
    image = _make_gradient_image(10, 5)
    rotated = rotate_image(image, 180)
    assert np.array_equal(rotated[0, 0], image[-1, -1])


def test_rotate_image_rejects_non_90_degree_values():
    image = _make_gradient_image(10, 10)
    with pytest.raises(ValueError):
        rotate_image(image, 45)


def test_crop_image_extracts_expected_region():
    image = _make_gradient_image(50, 40)
    cropped = crop_image(image, (10, 5, 20, 15))
    assert cropped.shape[:2] == (15, 20)
    assert np.array_equal(cropped, image[5:20, 10:30])


@pytest.mark.parametrize(
    "crop_rect",
    [
        (-1, 0, 10, 10),  # x 음수
        (0, -1, 10, 10),  # y 음수
        (0, 0, 0, 10),  # width 0
        (0, 0, 10, 0),  # height 0
        (45, 0, 10, 10),  # x+width가 이미지 범위 초과
        (0, 35, 10, 10),  # y+height가 이미지 범위 초과
    ],
)
def test_crop_image_rejects_invalid_rects(crop_rect):
    image = _make_gradient_image(50, 40)
    with pytest.raises(ValueError):
        crop_image(image, crop_rect)


def test_apply_manual_correction_rotates_before_cropping():
    """회전 먼저 → 그 결과 기준으로 자르기가 적용되는지 확인한다.

    30x20(가로x세로) 이미지를 90도 회전하면 20x30이 되므로, 회전 후 이미지
    기준의 자르기 좌표(0, 0, 20, 30 전체)가 유효해야 한다 — 회전 전 좌표계
    기준이었다면 범위를 벗어나 예외가 났을 것이다.
    """
    image = _make_gradient_image(30, 20)
    result = apply_manual_correction(image, rotation_degrees=90, crop_rect=(0, 0, 20, 30))
    assert result.shape[:2] == (30, 20)
    assert np.array_equal(result, rotate_image(image, 90))


def test_apply_manual_correction_without_crop_rect_only_rotates():
    image = _make_gradient_image(30, 20)
    result = apply_manual_correction(image, rotation_degrees=180, crop_rect=None)
    assert np.array_equal(result, rotate_image(image, 180))
