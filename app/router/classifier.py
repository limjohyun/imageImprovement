"""RT-1: 전처리된 이미지를 텍스트/도형/악보 중 하나로 분류한다.

무거운 ML 분류기 대신 결정론적 OpenCV 휴리스틱만 사용한다(Phase2 범위에서는
이 정도로 충분하다는 전제, `docs/roadmap.md` Phase2-1 참고). 판단 순서는:

1. 오선(악보 특유의 5개 평행 등간격 가로줄) 패턴이 보이면 `SCORE`.
2. 그렇지 않고, 페이지 면적 대비 큰 폐곡선(사각형/원 등 도형 윤곽)이 여러 개이면서
   글자 크기의 작은 컴포넌트가 상대적으로 적으면 `DIAGRAM`.
3. 그 외에는 `TEXT`(가장 널리 구현된 안전한 기본값).

`override`가 주어지면 위 자동 추정을 완전히 건너뛰고 그 값을 그대로 쓴다 — GUI 등
호출자가 자동 분류 오류를 수동으로 바로잡을 수 있어야 하기 때문이다.

Phase4-4(RT-1,2 고도화): Phase2-1 리뷰에서 알려진 한계로 남겨뒀던 오탐 시나리오
중 두 가지를 보정한다(`docs/roadmap.md` Phase2-1 완료 기록 참고):

- 줄무늬 배경 → SCORE 오탐: 오선 후보 줄만 있고 그 위/사이에 음표머리 같은 다른
  내용이 전혀 없으면 실제 오선이 아니라고 본다(`_has_non_line_content_near`) —
  긴 가로선 성분을 제거하고 남은 잔여 전경이 오선 후보 대역 안에 있는지 확인한다.
- 텍스트 라벨 없는 단일 대형 도형 → TEXT 오탐: 큰 도형이 딱 하나뿐이면 일반 도형
  조건(`_DIAGRAM_MIN_LARGE_COMPONENTS`)을 만족하지 못해 기본값 TEXT로 떨어졌다.
  페이지에 글자 크기의 컴포넌트가 전혀 없을 때만(제목/라벨 등과 혼동할 위험이
  없을 때만) 예외적으로 DIAGRAM으로 판정하는 엄격한 별도 조건을 추가했다.

세 번째로 남아있던 표(격자) 문서 → DIAGRAM 오탐은 두 차례(면적 변동계수 방식,
`cv2.HoughLinesP` 격자선 검출 방식) 재설계를 시도했으나 매번 code-reviewer가
새로운 HIGH급 회귀(실사진 지터 취약성, 회전 각도에 대한 취약성, PRD가 명시하는
흔한 도형 레이아웃의 오탐)를 발견해 순수 기하학적 휴리스틱으로는 이 프로젝트
범위에서 수렴하지 않는다고 판단, Phase4-4 범위에서 제외했다. 이 오탐은 GUI의
수동 유형 오버라이드(Part B)로 대응 가능한 "알려진 한계"로 남긴다.
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

# 오선 vs 줄무늬 배경 구분 파라미터 (Phase4-4).
_STAFF_RESIDUAL_MARGIN_RATIO = 0.6  # 오선 대역 위/아래로 몇 줄 간격만큼 여유를 두고 살펴볼지.
# 오선 대역 안에 이 비율 이상 "선이 아닌" 전경이 있어야 진짜 오선으로 본다.
_STAFF_RESIDUAL_MIN_FILL_RATIO = 0.001

# 도형 판정 파라미터.
_SMALL_COMPONENT_MIN_HEIGHT_RATIO = 0.005
_SMALL_COMPONENT_MAX_HEIGHT_RATIO = 0.05
_LARGE_COMPONENT_MIN_AREA_RATIO = 0.01
_DIAGRAM_MIN_LARGE_COMPONENTS = 2
_DIAGRAM_MAX_SMALL_TO_LARGE_RATIO = 3

# 단일 대형 도형 오탐 방지 파라미터 (Phase4-4): 큰 컴포넌트가 정확히 하나뿐이고
# 페이지에 글자 크기 컴포넌트가 전혀 없을 때만 예외적으로 DIAGRAM으로 판정한다.
_SINGLE_LARGE_DIAGRAM_MIN_AREA_RATIO = 0.03
_SINGLE_LARGE_DIAGRAM_MAX_SMALL_COUNT = 0


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


def _horizontal_line_mask(binary: np.ndarray) -> np.ndarray:
    """가로 폭의 상당 부분을 가로지르는 긴 수평선 성분만 남긴 마스크를 만든다.

    형태학적 열림(가로로 긴 커널)을 쓰면 문자/음표머리처럼 폭이 좁은 성분은
    사라지고 실제로 긴 가로선(오선, 줄무늬 배경 등)만 남는다.
    """
    width = binary.shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 4, 1), 1))
    return cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)


def _find_long_horizontal_line_rows(horizontal_mask: np.ndarray) -> list[int]:
    """가로 폭의 절반 이상을 채우는 긴 수평선이 지나가는 행 인덱스 목록을 찾는다."""
    width = horizontal_mask.shape[1]
    row_fill = horizontal_mask.sum(axis=1) / 255
    threshold = width * _STAFF_LINE_ROW_FILL_RATIO
    return [row for row, fill in enumerate(row_fill) if fill >= threshold]


def _group_adjacent_positions(positions: list[float], max_gap: float) -> list[float]:
    """인접한 위치들을 하나의 선(굵기로 인한 중복 검출)으로 묶어 각 선의 대표 좌표를 반환한다."""
    if not positions:
        return []
    ordered = sorted(positions)
    groups: list[list[float]] = [[ordered[0]]]
    for position in ordered[1:]:
        if position - groups[-1][-1] <= max_gap:
            groups[-1].append(position)
        else:
            groups.append([position])
    return [sum(group) / len(group) for group in groups]


def _has_non_line_content_near(residual: np.ndarray, window_centers: list[float]) -> bool:
    """오선 후보 대역(줄 위/사이) 안에 긴 가로선이 아닌 내용(음표머리 등)이 있는지 확인한다.

    줄무늬 배경(커튼, 벽지 등)은 등간격 평행선이라는 조건만으로는 진짜 오선과
    구분되지 않는다. 실제 오선에는 음표머리/기둥/보표 기호처럼 순수한 긴 가로선이
    아닌 내용이 줄 주변에 반드시 존재하지만, 장식용 줄무늬는 그런 내용이 전혀 없다는
    점(Phase4-4에서 새로 추가한 판정 기준)으로 둘을 구분한다.
    """
    height = residual.shape[0]
    gap = (window_centers[-1] - window_centers[0]) / (len(window_centers) - 1)
    margin = _STAFF_RESIDUAL_MARGIN_RATIO * gap
    top = max(0, int(window_centers[0] - margin))
    bottom = min(height, int(window_centers[-1] + margin) + 1)
    window = residual[top:bottom, :]
    if window.size == 0:
        return False
    fill_ratio = float((window > 0).sum()) / window.size
    return fill_ratio >= _STAFF_RESIDUAL_MIN_FILL_RATIO


def _has_staff_line_pattern(binary: np.ndarray) -> bool:
    """오선(5개의 평행 등간격 가로줄) 패턴이 존재하는지 판정한다."""
    horizontal_mask = _horizontal_line_mask(binary)
    line_centers = _group_adjacent_positions(
        [float(row) for row in _find_long_horizontal_line_rows(horizontal_mask)],
        _STAFF_LINE_ROW_GROUP_GAP,
    )
    if len(line_centers) < _STAFF_LINE_MIN_COUNT:
        return False

    residual = cv2.subtract(binary, horizontal_mask)
    for start in range(len(line_centers) - _STAFF_LINE_MIN_COUNT + 1):
        window = line_centers[start : start + _STAFF_LINE_MIN_COUNT]
        gaps = np.diff(window)
        if gaps.mean() <= 0:
            continue
        coefficient_of_variation = gaps.std() / gaps.mean()
        is_evenly_spaced = coefficient_of_variation < _STAFF_LINE_SPACING_CV_THRESHOLD
        if is_evenly_spaced and _has_non_line_content_near(residual, window):
            return True
    return False


def _count_shape_components(binary: np.ndarray) -> tuple[int, int, list[float]]:
    """글자 크기의 작은 컴포넌트 수, 도형 크기의 큰 컴포넌트 수, 큰 컴포넌트들의 면적 목록을 센다.

    큰 컴포넌트의 면적 목록은 단일 대형 도형 오탐 방지(`_SINGLE_LARGE_DIAGRAM_*` 조건)에 쓴다.
    """
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = binary.shape
    page_area = height * width
    small_count = 0
    large_areas: list[float] = []
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
            large_areas.append(area)
    return small_count, len(large_areas), large_areas


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

    small_count, large_count, large_areas = _count_shape_components(binary)
    if (
        large_count >= _DIAGRAM_MIN_LARGE_COMPONENTS
        and small_count < large_count * _DIAGRAM_MAX_SMALL_TO_LARGE_RATIO
    ):
        return DocumentType.DIAGRAM

    height, width = binary.shape
    page_area = height * width
    if (
        large_count == 1
        and small_count <= _SINGLE_LARGE_DIAGRAM_MAX_SMALL_COUNT
        and large_areas[0] >= _SINGLE_LARGE_DIAGRAM_MIN_AREA_RATIO * page_area
    ):
        return DocumentType.DIAGRAM

    return DocumentType.TEXT
