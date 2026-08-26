"""RT-1: 전처리된 이미지를 텍스트/도형/악보 중 하나로 분류한다.

무거운 ML 분류기 대신 결정론적 OpenCV 휴리스틱만 사용한다(Phase2 범위에서는
이 정도로 충분하다는 전제, `docs/roadmap.md` Phase2-1 참고). 판단 순서는:

1. 오선(악보 특유의 5개 평행 등간격 가로줄) 패턴이 보이면 `SCORE`.
2. 그렇지 않고, 페이지 면적 대비 큰 폐곡선(사각형/원 등 도형 윤곽)이 여러 개이면서
   글자 크기의 작은 컴포넌트가 상대적으로 적으면 `DIAGRAM`.
3. 그 외에는 `TEXT`(가장 널리 구현된 안전한 기본값).

`override`가 주어지면 위 자동 추정을 완전히 건너뛰고 그 값을 그대로 쓴다 — GUI 등
호출자가 자동 분류 오류를 수동으로 바로잡을 수 있어야 하기 때문이다.
"""

from __future__ import annotations

import enum

import cv2
import numpy as np

# 이미지 가장자리에는 원근보정/deskew 과정에서 생기는 얇은 테두리 아티팩트가 남을 수
# 있다. 이 테두리가 findContours에서 문서 전체를 감싸는 거대한 윤곽선 하나로 잡혀
# 실제 컴포넌트(글자/도형)를 가려버리는 문제가 있어, 분석 전 가장자리를 잘라낸다.
_ANALYSIS_MARGIN_RATIO = 0.02

# 오선 판정 파라미터.
_STAFF_LINE_MIN_COUNT = 5
_STAFF_LINE_ROW_GROUP_GAP = 3
_STAFF_LINE_SPACING_CV_THRESHOLD = 0.25  # 변동계수(표준편차/평균)가 이 값 미만이면 등간격으로 본다.
_STAFF_LINE_ROW_FILL_RATIO = 0.5  # 오선 후보 행이 가로 폭의 몇 %를 채워야 하는지.

# 도형 판정 파라미터.
_SMALL_COMPONENT_MIN_HEIGHT_RATIO = 0.005
_SMALL_COMPONENT_MAX_HEIGHT_RATIO = 0.05
_LARGE_COMPONENT_MIN_AREA_RATIO = 0.01
_DIAGRAM_MIN_LARGE_COMPONENTS = 2
_DIAGRAM_MAX_SMALL_TO_LARGE_RATIO = 3


class DocumentType(enum.Enum):
    """라우팅 대상 문서 유형 3종 (docs/prd.md §5.2)."""

    TEXT = "text"
    DIAGRAM = "diagram"
    SCORE = "score"


def _binarize_for_analysis(image: np.ndarray) -> np.ndarray:
    """분석용 이진 이미지(전경=255)를 만든다. 가장자리 테두리 아티팩트는 잘라낸다."""
    if image.size == 0:
        raise ValueError("빈 이미지는 분류할 수 없습니다.")
    if image.dtype != np.uint8:
        raise ValueError(f"8비트 이미지가 필요합니다 (입력 dtype: {image.dtype}).")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape
    margin_y = int(height * _ANALYSIS_MARGIN_RATIO)
    margin_x = int(width * _ANALYSIS_MARGIN_RATIO)
    cropped = gray[margin_y : height - margin_y, margin_x : width - margin_x]
    _, binary = cv2.threshold(cropped, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def _find_long_horizontal_line_rows(binary: np.ndarray) -> list[int]:
    """가로 폭의 절반 이상을 채우는 긴 수평선이 지나가는 행 인덱스 목록을 찾는다."""
    height, width = binary.shape
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 4, 1), 1))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    row_fill = horizontal.sum(axis=1) / 255
    threshold = width * _STAFF_LINE_ROW_FILL_RATIO
    return [row for row, fill in enumerate(row_fill) if fill >= threshold]


def _group_adjacent_rows(rows: list[int]) -> list[float]:
    """인접한 행 인덱스를 하나의 선(굵기)으로 묶어 각 선의 중심 좌표 목록을 반환한다."""
    if not rows:
        return []
    groups: list[list[int]] = [[rows[0]]]
    for row in rows[1:]:
        if row - groups[-1][-1] <= _STAFF_LINE_ROW_GROUP_GAP:
            groups[-1].append(row)
        else:
            groups.append([row])
    return [sum(group) / len(group) for group in groups]


def _has_staff_line_pattern(binary: np.ndarray) -> bool:
    """오선(5개의 평행 등간격 가로줄) 패턴이 존재하는지 판정한다."""
    line_centers = _group_adjacent_rows(_find_long_horizontal_line_rows(binary))
    if len(line_centers) < _STAFF_LINE_MIN_COUNT:
        return False

    for start in range(len(line_centers) - _STAFF_LINE_MIN_COUNT + 1):
        window = np.array(line_centers[start : start + _STAFF_LINE_MIN_COUNT])
        gaps = np.diff(window)
        if gaps.mean() <= 0:
            continue
        coefficient_of_variation = gaps.std() / gaps.mean()
        if coefficient_of_variation < _STAFF_LINE_SPACING_CV_THRESHOLD:
            return True
    return False


def _count_shape_components(binary: np.ndarray) -> tuple[int, int]:
    """글자 크기의 작은 컴포넌트 수와 도형 크기의 큰 컴포넌트 수를 센다."""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = binary.shape
    page_area = height * width
    small_count = 0
    large_count = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area <= 0:
            continue
        _, _, _, box_height = cv2.boundingRect(contour)
        relative_height = box_height / height
        is_char_sized_height = (
            _SMALL_COMPONENT_MIN_HEIGHT_RATIO <= relative_height
            <= _SMALL_COMPONENT_MAX_HEIGHT_RATIO
        )
        if is_char_sized_height and area < _LARGE_COMPONENT_MIN_AREA_RATIO * page_area:
            small_count += 1
        elif area >= _LARGE_COMPONENT_MIN_AREA_RATIO * page_area:
            large_count += 1
    return small_count, large_count


def classify_document_type(
    image: np.ndarray, *, override: DocumentType | None = None
) -> DocumentType:
    """RT-1: 전처리된 이미지 한 장을 텍스트/도형/악보 중 하나로 분류한다.

    `override`가 주어지면 자동 추정을 건너뛰고 그 값을 그대로 반환한다(수동 오버라이드).
    """
    if override is not None:
        return override

    binary = _binarize_for_analysis(image)

    if _has_staff_line_pattern(binary):
        return DocumentType.SCORE

    small_count, large_count = _count_shape_components(binary)
    if (
        large_count >= _DIAGRAM_MIN_LARGE_COMPONENTS
        and small_count < large_count * _DIAGRAM_MAX_SMALL_TO_LARGE_RATIO
    ):
        return DocumentType.DIAGRAM

    return DocumentType.TEXT
