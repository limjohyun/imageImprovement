"""GUI-3(일부): 사용자가 직접 지정하는 자르기/회전 보정.

PRE-1~4(원근보정/deskew/조명보정/업스케일)와 달리 자동으로 추정하지 않고,
GUI(`app.gui.crop_rotate_dialog.CropRotateDialog`)에서 사용자가 숫자로 지정한
값을 그대로 적용하는 순수 이미지 변환이다. Qt에 의존하지 않으므로 pytest로
바로 검증할 수 있다.

적용 순서는 항상 **회전 먼저 → 그 결과 기준으로 자르기**다. 자르기 좌표
(x/y/width/height)를 회전 후 이미지 기준으로 지정하는 편이 사용자에게
직관적이기 때문이다(예: 세로로 촬영된 사진을 90도 돌려 가로로 맞춘 뒤, 그
가로 이미지에서 원하는 영역만 자르는 흐름). 이 순서는 `CropRotateDialog`가
자르기 스핀박스의 유효 범위를 계산할 때도 동일하게 가정한다.

회전은 90도 단위(0/90/180/270)만 지원한다 — 임의 각도 회전은 PRE-2(자동
deskew)가 이미 처리하므로 이번 범위 밖이다.
"""

from __future__ import annotations

import cv2
import numpy as np

_ROTATION_CV2_CODES: dict[int, int | None] = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def rotate_image(image: np.ndarray, degrees: int) -> np.ndarray:
    """90도 단위로 이미지를 회전한다 (0/90/180/270만 지원, 정보 손실 없음)."""
    if degrees not in _ROTATION_CV2_CODES:
        raise ValueError(f"90도 단위(0/90/180/270)만 지원합니다: {degrees}")
    code = _ROTATION_CV2_CODES[degrees]
    return image if code is None else cv2.rotate(image, code)


def crop_image(image: np.ndarray, crop_rect: tuple[int, int, int, int]) -> np.ndarray:
    """`(x, y, width, height)` 영역으로 이미지를 자른다.

    좌표는 반드시 `image`의 크기 기준으로 유효해야 한다(x/y는 0 이상, width/height는
    양수, x+width/y+height가 이미지 범위를 넘지 않음) — 그렇지 않으면 잘못된 다이얼로그
    입력을 조용히 잘라내는 대신 바로 예외로 드러낸다.
    """
    x, y, width, height = crop_rect
    image_height, image_width = image.shape[:2]
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError(f"자르기 좌표가 올바르지 않습니다: {crop_rect}")
    if x + width > image_width or y + height > image_height:
        raise ValueError(
            f"자르기 영역이 이미지 범위를 벗어납니다: {crop_rect}, "
            f"이미지 크기=({image_width}, {image_height})"
        )
    return image[y : y + height, x : x + width]


def apply_manual_correction(
    image: np.ndarray,
    *,
    rotation_degrees: int = 0,
    crop_rect: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """GUI-3: 회전을 먼저 적용한 뒤, 그 결과 기준으로 자르기를 적용한다.

    `crop_rect`가 `None`이면 회전만 적용하고 자르기는 건너뛴다(전체 영역 선택과
    동일한 효과이지만, 좌표 유효성 검증을 아예 거치지 않아도 되게 한다).
    """
    result = rotate_image(image, rotation_degrees)
    if crop_rect is not None:
        result = crop_image(result, crop_rect)
    return result
