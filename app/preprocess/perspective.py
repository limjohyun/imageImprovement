"""PRE-1: 문서 영역 검출 + 원근 보정.

Canny 엣지 + contour로 이미지 안의 문서 윤곽(사각형)을 자동 검출한 뒤
`cv2.getPerspectiveTransform`/`warpPerspective`로 정면 뷰로 평탄화한다.

자동 검출이 실패해도 파이프라인이 멈추지 않도록, "자동 검출"과 "평탄화 적용"을
서로 다른 함수로 분리해뒀다. GUI(Phase1-5 이후)는 자동 검출이 실패했을 때
`DocumentCornersNotFoundError`를 잡아 사용자가 지정한 4점 좌표를
`correct_perspective(image, corners=...)`로 그대로 넘기면 된다.

입력 이미지는 BGR uint8을 가정한다(OpenCV 기본 채널 순서). RGB 배열을 그대로
넘기면 색상 채널이 반전된 채로 처리되니 주의.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class DocumentCornersNotFoundError(RuntimeError):
    """자동 문서 윤곽 검출에 실패했을 때 발생한다.

    호출자(GUI 등)는 이 예외를 잡아 사용자가 수동으로 지정한 4점 좌표를
    `correct_perspective(image, corners=...)`에 넘겨 재시도해야 한다.
    """


def _order_corners(points: np.ndarray) -> np.ndarray:
    """임의 순서의 4점을 (좌상, 우상, 우하, 좌하) 순서로 정렬한다.

    과거에는 "x+y 최소/최대 → 좌상/우하", "y-x 최소/최대 → 우상/좌하"라는
    표준 order-points 휴리스틱을 썼다. 이 방식은 좌표축 기준(가로/세로)으로
    점을 나누기 때문에, 문서가 화면상 약 45도 이상 회전되어 촬영되면 "어느 점이
    더 좌상단에 가까운가"의 기준 자체가 애매해져 좌상/좌하 또는 우상/좌하가
    통째로 뒤바뀌는 문제가 있었다(회귀 테스트: 44도는 정상, 46도부터 종횡비 반전).

    새 구현은 두 단계로 나눠 이 문제를 해결한다.

    1) 4점의 무게중심 기준 atan2 각도로 정렬해, 회전 각도와 무관하게 항상 올바른
       "변 구조"(인접 관계)를 얻는다 — 볼록四각형은 무게중심 기준 각도순 정렬이
       곧 다각형 순회 순서와 일치한다는 성질을 이용한다.
    2) 인접한 변 중 더 짧은 변 쌍을 "가로(폭)" 변으로 삼는다. 변 길이는 촬영
       각도(화면상 절대 방향)와 무관한 값이라, 같은 물리적 문서를 어떤 각도로
       찍든 위/아래로 지정되는 변이 항상 일관되게 나온다.

    한계: 위 2)번 규칙은 "짧은 변=폭"이라는 관례를 강제하므로, 실제로는 가로가
    더 긴(landscape) 문서를 정면에 가깝게 찍은 경우에도 출력이 세로로 긴
    캔버스로 나올 수 있다. 4개 모서리 좌표만으로는 원본 문서가 portrait인지
    landscape인지 판별할 근본적인 방법이 없어(두 경우가 촬영 각도만 다르게
    본 동일한 좌표 집합으로 나타날 수 있음) 감수하는 한계이며, 필요하면 GUI의
    수동 모서리 지정(`correct_perspective(image, corners=...)`)으로 우회한다.
    정사각형처럼 완전히 대칭인 문서는 이 방식으로도 원래 방향을 복원할 수 없다.
    """
    pts = points.astype(np.float32).reshape(4, 2)
    centroid = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - centroid[1], pts[:, 0] - centroid[0])
    ring = pts[np.argsort(angles)]

    # ring[i] -> ring[i+1] 변의 길이. (0,2)번 변 쌍과 (1,3)번 변 쌍이 사각형의
    # 서로 마주보는 두 변 쌍(가로/세로)에 해당한다.
    edge_lengths = np.linalg.norm(np.roll(ring, -1, axis=0) - ring, axis=1)
    if edge_lengths[1] + edge_lengths[3] < edge_lengths[0] + edge_lengths[2]:
        ring = np.roll(ring, -1, axis=0)

    # 남은 애매함(180도 대칭)은 화면 좌상단에 더 가까운(x+y가 더 작은) 점을
    # 시작점으로 골라 해소한다.
    candidates = (ring, np.roll(ring, -2, axis=0))
    ordered = min(candidates, key=lambda candidate: float(candidate[0].sum()))
    return ordered.astype(np.float32)


def detect_document_corners(
    image: np.ndarray, *, min_area_ratio: float = 0.1
) -> np.ndarray | None:
    """이미지 안에서 문서로 추정되는 4각형 윤곽의 모서리 좌표(shape (4, 2))를 찾는다.

    사각형 윤곽을 못 찾거나 너무 작으면(배경 대비가 약해 잡음 윤곽만 잡히는 경우)
    None을 반환한다 — 예외를 던지지 않는 이유는 이 함수는 "시도"만 담당하고,
    실패 처리(수동 지정 요구 등)는 상위 `correct_perspective`가 맡기 때문이다.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 100)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_area = image.shape[0] * image.shape[1]
    # 면적 내림차순으로 상위 몇 개만 검사한다: 문서 윤곽은 배경보다 훨씬 크게 잡히므로
    # 대부분 최상위 후보에서 발견되고, 정렬돼 있어 임계값 미만이면 이후도 더 작으니 즉시 중단한다.
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(contour)
        if area < image_area * min_area_ratio:
            break
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return _order_corners(approx.reshape(4, 2).astype(np.float32))

    logger.info("문서 4각형 윤곽을 찾지 못했습니다 (min_area_ratio=%s)", min_area_ratio)
    return None


def warp_to_corners(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """주어진 4모서리 좌표를 이용해 문서를 정면 뷰로 평탄화한다.

    자동 검출 결과와 수동 지정 좌표 모두 이 함수를 공용 진입점으로 사용한다.
    corners는 (좌상, 우상, 우하, 좌하) 순서의 (4, 2) 배열이어야 한다.
    """
    corners = np.asarray(corners, dtype=np.float32)
    if corners.shape != (4, 2):
        raise ValueError(f"corners는 (4, 2) shape이어야 합니다: {corners.shape}")

    top_left, top_right, bottom_right, bottom_left = corners
    width_top = np.linalg.norm(top_right - top_left)
    width_bottom = np.linalg.norm(bottom_right - bottom_left)
    max_width = max(int(width_top), int(width_bottom))

    height_left = np.linalg.norm(bottom_left - top_left)
    height_right = np.linalg.norm(bottom_right - top_right)
    max_height = max(int(height_left), int(height_right))

    if max_width <= 0 or max_height <= 0:
        raise ValueError("corners로부터 유효한 출력 크기를 계산할 수 없습니다.")

    destination = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def correct_perspective(image: np.ndarray, *, corners: np.ndarray | None = None) -> np.ndarray:
    """PRE-1 진입점: 문서 영역 검출 + 원근 보정.

    - `corners`를 넘기면(수동 지정, 예: GUI에서 사용자가 4점을 찍은 경우) 그 값을
      그대로 사용해 평탄화한다.
    - 생략하면 `detect_document_corners`로 자동 검출을 시도한다.
    - 자동 검출에 실패하면 `DocumentCornersNotFoundError`를 던진다 — 호출자가
      이를 잡아 수동 좌표를 받아 재호출하도록 유도하기 위함이다.
    """
    if corners is not None:
        return warp_to_corners(image, corners)

    detected = detect_document_corners(image)
    if detected is None:
        raise DocumentCornersNotFoundError(
            "문서 4모서리를 자동으로 검출하지 못했습니다. "
            "correct_perspective(image, corners=...)로 수동 좌표를 지정하세요."
        )
    return warp_to_corners(image, detected)
