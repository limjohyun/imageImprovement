"""RT-1 수용 기준 검증: 텍스트/도형/악보 자동 분류 + 수동 오버라이드."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.router.classifier import DocumentType, classify_document_type
from tests.fixtures.synthetic import SyntheticPhoto


def _preprocessed(photo: SyntheticPhoto) -> np.ndarray:
    """라우터는 전처리된 이미지를 입력받는다고 가정하므로 공통 파이프라인을 거친다."""
    return run_pipeline(photo.photo, PreprocessConfig())


def _make_staff_line_image(width: int = 1000, height: int = 1300) -> np.ndarray:
    """오선 5줄 + 음표를 흉내낸 작은 타원을 그린 합성 악보 이미지.

    MuseScore가 설치돼 있지 않아도(Phase3 착수 전) 오선 검출 휴리스틱을
    검증할 수 있도록, `tests.fixtures.synthetic.make_score_photo()`에 의존하지
    않고 직접 그린다.
    """
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    staff_top, staff_gap = 300, 30
    for i in range(5):
        y = staff_top + i * staff_gap
        cv2.line(image, (100, y), (900, y), (0, 0, 0), 3)
    for cx in (200, 300, 400, 500, 600, 700):
        cv2.ellipse(image, (cx, staff_top + 60), (14, 10), -20, 0, 360, (0, 0, 0), -1)
    return image


def test_classify_text_photo_as_text(synthetic_text_photo: SyntheticPhoto) -> None:
    document_type = classify_document_type(_preprocessed(synthetic_text_photo))
    assert document_type is DocumentType.TEXT


def test_classify_diagram_photo_as_diagram(synthetic_diagram_photo: SyntheticPhoto) -> None:
    document_type = classify_document_type(_preprocessed(synthetic_diagram_photo))
    assert document_type is DocumentType.DIAGRAM


def test_classify_staff_line_image_as_score() -> None:
    document_type = classify_document_type(_make_staff_line_image())
    assert document_type is DocumentType.SCORE


@pytest.mark.parametrize("override", list(DocumentType))
def test_manual_override_bypasses_heuristic(
    synthetic_text_photo: SyntheticPhoto, override: DocumentType
) -> None:
    """수동 오버라이드가 주어지면 자동 추정과 무관하게 그 값을 그대로 반환해야 한다."""
    document_type = classify_document_type(_preprocessed(synthetic_text_photo), override=override)
    assert document_type is override


def test_classify_empty_image_raises_value_error() -> None:
    with pytest.raises(ValueError, match="빈 이미지"):
        classify_document_type(np.zeros((0, 0, 3), dtype=np.uint8))


def test_classify_non_uint8_image_raises_value_error() -> None:
    with pytest.raises(ValueError, match="8비트"):
        classify_document_type(np.full((500, 400, 3), 255, dtype=np.float32))
