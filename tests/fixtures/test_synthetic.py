"""합성 fixture 생성 유틸리티(tests/fixtures/synthetic.py) 자체가 제대로 동작하는지 검증한다.

이후 Phase들이 `synthetic_text_photo` 등을 신뢰하고 재사용할 수 있으려면, 왜곡이
실제로 적용되고 있는지(원본과 달라짐)와 재현성(같은 시드 → 같은 결과)을 여기서
먼저 증명해 둔다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np

from tests.fixtures.synthetic import (
    DEFAULT_TEXT_LINES,
    SyntheticPhoto,
    _build_synthetic_score,
    find_musescore_executable,
    make_diagram_photo,
    make_text_photo,
)


def test_text_photo_shape_and_type() -> None:
    result = make_text_photo()
    assert isinstance(result, SyntheticPhoto)
    assert result.photo.dtype == np.uint8
    assert result.photo.ndim == 3 and result.photo.shape[2] == 3
    assert result.ground_truth.dtype == np.uint8
    assert result.corners.shape == (4, 2)
    assert result.text == "\n".join(DEFAULT_TEXT_LINES)


def test_diagram_photo_has_no_text() -> None:
    result = make_diagram_photo()
    assert result.text is None
    assert result.corners.shape == (4, 2)


def test_photo_is_distorted_relative_to_ground_truth() -> None:
    """왜곡(배경 합성+원근+저해상도화)이 실제로 적용됐는지 확인한다."""
    result = make_text_photo()
    # 배경 마진 합성 + 다운샘플이 적용되므로 픽셀 크기 자체가 원본과 달라야 한다.
    assert result.photo.shape != result.ground_truth.shape
    # 문서 corners는 캔버스 안쪽 어딘가에 있어야 하고, 음수/NaN 등 깨진 값이 없어야 한다.
    assert np.isfinite(result.corners).all()
    height, width = result.photo.shape[:2]
    margin = max(width, height) * 0.5  # 원근 왜곡으로 약간 캔버스 밖으로 나갈 수 있어 여유를 둔다
    assert (result.corners[:, 0] > -margin).all()
    assert (result.corners[:, 0] < width + margin).all()
    assert (result.corners[:, 1] > -margin).all()
    assert (result.corners[:, 1] < height + margin).all()


def test_same_seed_is_deterministic() -> None:
    first = make_text_photo(seed=123)
    second = make_text_photo(seed=123)
    np.testing.assert_array_equal(first.photo, second.photo)
    np.testing.assert_array_equal(first.corners, second.corners)


def test_different_seed_changes_distortion() -> None:
    first = make_diagram_photo(seed=1)
    second = make_diagram_photo(seed=2)
    # 시드가 다르면 왜곡(원근 지터/조명/노이즈)이 달라져 같은 해상도라도 픽셀이 달라진다.
    assert first.photo.shape == second.photo.shape
    assert not np.array_equal(first.photo, second.photo)


def test_find_musescore_executable_returns_path_or_none() -> None:
    """실행 파일 탐색 함수는 예외 없이 Path 또는 None만 반환해야 한다 (설치 여부와 무관하게)."""
    result = find_musescore_executable()
    assert result is None or result.exists()


def test_score_photo_via_fixture_or_skips(synthetic_score_photo: SyntheticPhoto) -> None:
    """MuseScore가 설치돼 있으면 촬영본이 생성되고, 없으면 conftest가 자동으로 skip한다."""
    assert synthetic_score_photo.photo.dtype == np.uint8
    assert synthetic_score_photo.corners.shape == (4, 2)


def test_build_synthetic_score_produces_well_formed_musicxml(tmp_path) -> None:
    """MuseScore 유무와 무관하게, music21 MusicXML 생성 로직 자체를 검증한다.

    make_score_photo()는 MuseScore가 없으면 이 코드를 호출하기 전에 skip돼
    회귀를 못 잡으므로, MusicXML 작성 부분만 별도로 exercise한다.
    """
    score = _build_synthetic_score()
    musicxml_path = tmp_path / "score.musicxml"
    score.write("musicxml", fp=str(musicxml_path))

    xml_text = musicxml_path.read_text(encoding="utf-8")
    root = ET.fromstring(xml_text)  # well-formed XML이 아니면 여기서 예외가 발생한다
    assert root.tag == "score-partwise"
    pitch_steps = [step.text for step in root.iter("step")]
    assert pitch_steps == ["C", "D", "E", "F", "G", "A", "B", "C"]
