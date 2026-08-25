"""PRE-4 수용 기준 검증: 전처리 전/후 OCR 인식률 비교.

PRD PRE-4의 수용 기준은 "저해상도·노이즈가 있는 입력을 업스케일 처리해 후속
OCR/OMR 인식률이 원본 대비 향상됨을 확인한다"이다. 실제 OCR 처리기(TXT-1,
`processors/text.py`)는 아직 Phase1-3 대상이므로, 여기서는 이미 의존성에 포함된
`pytesseract`를 검증 도구로만 사용해 파이프라인 적용 전/후의 OCR 문자열이 정답
텍스트와 얼마나 유사한지(difflib) 비교한다. tesseract 바이너리가 PATH에 없으면
(예: 이 저장소를 아직 Phase1-3 설치 전 상태로 여는 경우) 스스로 skip한다.
"""

from __future__ import annotations

import difflib
import shutil

import cv2
import pytest

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from tests.fixtures.synthetic import _photograph, _render_text_document

pytesseract = pytest.importorskip("pytesseract")

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


def _similarity(candidate: str, expected: str) -> float:
    return difflib.SequenceMatcher(None, candidate, expected).ratio()


@pytest.mark.skipif(not _TESSERACT_AVAILABLE, reason="tesseract 바이너리가 PATH에 없습니다.")
def test_preprocessing_pipeline_improves_ocr_accuracy():
    """저해상도+노이즈+원근왜곡 촬영본을 전처리하면 OCR 인식률이 원본 대비 향상돼야 한다."""
    document, text = _render_text_document()
    # 기본 fixture(make_text_photo)보다 더 가혹하게 왜곡해야 raw OCR과의 격차가
    # 안정적으로 드러난다(기본 왜곡 강도는 tesseract가 이미 꽤 잘 처리해 차이가 작음).
    photo, corners = _photograph(
        document, noise_sigma=12.0, downsample_scale=0.28, max_jitter_ratio=0.07
    )

    raw_text = pytesseract.image_to_string(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY))

    config = PreprocessConfig(corners=corners, upscale_scale=3.0)
    processed = run_pipeline(photo, config)
    processed_text = pytesseract.image_to_string(cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY))

    raw_similarity = _similarity(raw_text, text)
    processed_similarity = _similarity(processed_text, text)
    assert processed_similarity > raw_similarity
