"""PRE-1(문서 영역 검출 + 원근 보정) 테스트."""

from __future__ import annotations

import numpy as np
import pytest

from app.preprocess.perspective import (
    DocumentCornersNotFoundError,
    _order_corners,
    correct_perspective,
    detect_document_corners,
    warp_to_corners,
)


def _match_error(detected: np.ndarray, expected: np.ndarray) -> float:
    """정렬된 두 4점 집합 사이의 평균 유클리드 거리(px)."""
    return float(np.linalg.norm(detected - expected, axis=1).mean())


def test_detect_document_corners_matches_known_corners(synthetic_text_photo):
    """자동 검출된 4모서리가 fixture가 알려주는 실제 좌표와 충분히 가까워야 한다."""
    detected = detect_document_corners(synthetic_text_photo.photo)
    assert detected is not None
    # 합성 fixture는 노이즈/조명 왜곡이 있어 픽셀 단위로 완전히 일치하진 않지만,
    # 원근보정에 쓰기에 충분히 정확한지(문서 크기 대비 오차가 작은지)만 확인한다.
    error = _match_error(detected, synthetic_text_photo.corners)
    assert error < 10.0, f"평균 모서리 오차가 너무 큽니다: {error}px"


def test_detect_document_corners_matches_diagram_photo(synthetic_diagram_photo):
    """도형 문서에서도 동일하게 검출이 동작해야 한다(문서 유형 무관 공통 모듈)."""
    detected = detect_document_corners(synthetic_diagram_photo.photo)
    assert detected is not None
    error = _match_error(detected, synthetic_diagram_photo.corners)
    assert error < 10.0


def test_detect_document_corners_returns_none_without_contrast():
    """배경과 구분되는 윤곽이 없으면(균일한 색) None을 반환해야 한다(예외 아님)."""
    flat_image = np.full((200, 200, 3), 128, dtype=np.uint8)
    assert detect_document_corners(flat_image) is None


def test_correct_perspective_auto_detection_flattens_document(synthetic_text_photo):
    """자동 검출 경로로 보정한 결과가 원본 문서와 비슷한 종횡비를 가져야 한다."""
    warped = correct_perspective(synthetic_text_photo.photo)
    gt_h, gt_w = synthetic_text_photo.ground_truth.shape[:2]
    warped_h, warped_w = warped.shape[:2]
    expected_ratio = gt_h / gt_w
    actual_ratio = warped_h / warped_w
    assert actual_ratio == pytest.approx(expected_ratio, rel=0.1)


def test_correct_perspective_manual_corners_matches_auto(synthetic_text_photo):
    """수동으로 4점을 지정하는 경로(GUI 연동용)도 정상 동작해야 한다."""
    manual = correct_perspective(synthetic_text_photo.photo, corners=synthetic_text_photo.corners)
    auto = correct_perspective(synthetic_text_photo.photo)
    # 자동 검출 좌표와 정답 좌표가 아주 가까우므로 두 결과의 크기도 비슷해야 한다.
    assert manual.shape[0] == pytest.approx(auto.shape[0], rel=0.1)
    assert manual.shape[1] == pytest.approx(auto.shape[1], rel=0.1)


def test_correct_perspective_raises_when_auto_detection_fails():
    """자동 검출 실패 시 예외를 던져 호출자가 수동 지정으로 재시도하게 해야 한다.

    PRE-1 수용 기준: "자동 검출 실패 시 사용자가 수동으로 4점을 지정할 수 있다".
    """
    flat_image = np.full((200, 200, 3), 128, dtype=np.uint8)
    with pytest.raises(DocumentCornersNotFoundError):
        correct_perspective(flat_image)


def test_warp_to_corners_rejects_wrong_shape():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        warp_to_corners(image, np.zeros((3, 2), dtype=np.float32))


def _rotated_rect_corners(width: float, height: float, angle_deg: float) -> np.ndarray:
    """폭/높이가 알려진 사각형을 무게중심 기준으로 angle_deg만큼 회전시킨 4모서리를 만든다.

    cv2.approxPolyDP가 반환하는 "임의 시작점"을 흉내내기 위해, 회전 후에도 굳이
    정렬하지 않고 (좌상, 우상, 우하, 좌하) 원래 순서 그대로 반환한다 —
    `_order_corners`가 이 순서 정보 없이도 스스로 올바르게 복원해야 한다.
    """
    base = np.array(
        [[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float64
    )
    center = base.mean(axis=0)
    theta = np.radians(angle_deg)
    rotation = np.array(
        [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]]
    )
    rotated = (base - center) @ rotation.T + center
    return rotated.astype(np.float32)


@pytest.mark.parametrize("angle_deg", [0, 15, 30, 44, 46, 60, 90])
def test_order_corners_preserves_aspect_ratio_across_rotation(angle_deg):
    """PRE-1 회귀 테스트: 45도 이상 회전된 입력에서도 종횡비가 뒤바뀌면 안 된다.

    과거 버그: `_order_corners`가 좌표합/좌표차 기반 휴리스틱을 써서 각도가 45도를
    넘어가는 순간 좌상/좌하(또는 우상/우하) 라벨이 통째로 뒤바뀌어, 폭 401 x 높이
    603(비율 1.5)짜리 문서가 46도 이상 회전된 사진에서는 폭/높이가 뒤집힌
    401x603 -> 603x401 형태(비율 0.67)로 잘못 평탄화됐다.
    """
    doc_width, doc_height = 401.0, 603.0
    expected_ratio = doc_height / doc_width

    corners = _rotated_rect_corners(doc_width, doc_height, angle_deg)
    ordered = _order_corners(corners)

    top_left, top_right, bottom_right, bottom_left = ordered
    out_width = max(
        np.linalg.norm(top_right - top_left), np.linalg.norm(bottom_right - bottom_left)
    )
    out_height = max(
        np.linalg.norm(bottom_left - top_left), np.linalg.norm(bottom_right - top_right)
    )
    actual_ratio = out_height / out_width
    assert actual_ratio == pytest.approx(expected_ratio, rel=0.02), (
        f"angle={angle_deg}도에서 종횡비가 반전됐습니다: "
        f"actual={actual_ratio:.3f}, expected={expected_ratio:.3f}"
    )


@pytest.mark.parametrize("angle_deg", [0, 44, 46, 90])
def test_correct_perspective_manual_corners_preserves_aspect_ratio_across_rotation(angle_deg):
    """`warp_to_corners`까지 거친 실제 출력 이미지 크기 기준으로도 동일하게 검증한다."""
    doc_width, doc_height = 401.0, 603.0
    expected_ratio = doc_height / doc_width

    corners = _rotated_rect_corners(doc_width, doc_height, angle_deg)
    ordered = _order_corners(corners)

    # 회전된 4점이 놓일 수 있을 만큼 넉넉한 캔버스를 준비한다.
    canvas_size = int(doc_width + doc_height) * 2
    image = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)

    warped = correct_perspective(image, corners=ordered)
    actual_ratio = warped.shape[0] / warped.shape[1]
    assert actual_ratio == pytest.approx(expected_ratio, rel=0.02), (
        f"angle={angle_deg}도에서 warp_to_corners 출력 종횡비가 반전됐습니다: "
        f"shape={warped.shape}"
    )
