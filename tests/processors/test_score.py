"""SCR-1 수용 기준 검증: 촬영된 악보 이미지가 MusicXML로 변환돼야 한다.

oemer OMR 체크포인트(.onnx/.h5, 수백MB)는 최초 실행 시 자동 다운로드되는
무거운 자산이라 이 테스트 스위트에서는 내려받지 않는다. 체크포인트가 없으면
`ScoreModelUnavailableError`가 실제로 발생하는지만 검증하고, 실제 인식까지
필요한 테스트는 `tests/fixtures/synthetic.py`의 관행대로 skip 처리한다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np
import pytest

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.score import (
    ScoreModelUnavailableError,
    _checkpoint_path,
    recognize_score,
)


def _preprocessed_score_photo(photo):
    config = PreprocessConfig(corners=photo.corners)
    return run_pipeline(photo.photo, config)


def test_recognize_score_raises_clear_error_when_checkpoints_missing(tmp_path):
    """체크포인트가 없으면 조용히 다운로드를 시도하지 않고 명확한 예외를 던져야 한다.

    이 머신에는 oemer 체크포인트를 의도적으로 내려받아두지 않았으므로, 이
    테스트는 실제로 예외 경로를 실행해 검증한다(체크포인트가 있는 머신에서는
    아래에서 skip된다). 체크포인트 확인은 실제 악보 내용을 들여다보기 전에
    가장 먼저 일어나므로, MuseScore 없이도 검증할 수 있도록 실제 악보 fixture
    대신 임의의 더미 이미지를 사용한다(MuseScore 설치 여부와 무관하게 이
    테스트가 돌아가야 하기 때문).
    """
    if _checkpoint_path().exists():
        pytest.skip("체크포인트가 이미 준비되어 있어 부재 경로를 검증할 수 없습니다")

    dummy_image = np.full((200, 200, 3), 255, dtype=np.uint8)
    output_musicxml = tmp_path / "score.musicxml"

    with pytest.raises(ScoreModelUnavailableError):
        recognize_score(dummy_image, output_musicxml)


def test_recognize_score_produces_valid_musicxml(synthetic_score_photo, tmp_path):
    """SCR-1: 체크포인트가 준비된 머신에서는 실제로 음표가 담긴 MusicXML을 생성해야 한다.

    이 저장소의 개발 머신에는 체크포인트를 의도적으로 내려받아두지 않았으므로
    (수백MB, 시간 소요), 없으면 skip한다 — CI/다른 머신에서 체크포인트를 준비해두면
    이 테스트가 실제로 실행된다.
    """
    if not _checkpoint_path().exists():
        pytest.skip("oemer 체크포인트가 준비되어 있지 않아 실제 OMR 인식을 실행할 수 없습니다.")

    processed = _preprocessed_score_photo(synthetic_score_photo)
    output_musicxml = tmp_path / "score.musicxml"

    result_path = recognize_score(processed, output_musicxml)

    assert result_path == output_musicxml
    assert output_musicxml.exists()

    root = ET.fromstring(output_musicxml.read_bytes())
    assert root.tag == "score-partwise"
    notes = root.findall(".//note")
    assert len(notes) > 0
