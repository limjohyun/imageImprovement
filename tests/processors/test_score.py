"""SCR-1/SCR-2 수용 기준 검증: 촬영된 악보 이미지가 MusicXML/재조판 PDF로 변환돼야 한다.

oemer OMR 체크포인트(.onnx/.h5, 수백MB)는 최초 실행 시 자동 다운로드되는
무거운 자산이라 이 테스트 스위트에서는 내려받지 않는다. 체크포인트가 없으면
`ScoreModelUnavailableError`가 실제로 발생하는지만 검증하고, 실제 인식까지
필요한 테스트는 `tests/fixtures/synthetic.py`의 관행대로 skip 처리한다.

SCR-2(재조판 PDF, MuseScore 연동)는 이 머신에 MuseScore 4가 설치되어 있으므로
`retypeset_score`가 실제로 mscore 서브프로세스를 실행하는 테스트로 검증한다 —
oemer 체크포인트 유무와는 무관하게(입력은 MusicXML이면 되므로) 항상 실행된다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np
import pymupdf
import pytest

from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.score import (
    ScoreModelUnavailableError,
    ScoreRendererUnavailableError,
    ScoreRenderingError,
    _checkpoint_path,
    find_musescore_executable,
    process_image,
    recognize_score,
    retypeset_score,
)
from tests.fixtures.synthetic import _build_synthetic_score


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


def _write_synthetic_musicxml(path):
    """oemer 없이도 SCR-2를 검증할 수 있도록 music21로 유효한 MusicXML을 직접 만든다."""
    _build_synthetic_score().write("musicxml", fp=str(path))


def test_retypeset_score_produces_valid_pdf(tmp_path):
    """SCR-2: MusicXML을 MuseScore로 재조판하면 유효한(페이지 1장 이상) PDF가 나와야 한다.

    이 머신에는 MuseScore 4가 설치돼 있으므로 실제로 mscore 서브프로세스를
    실행한다. oemer 체크포인트와는 무관하게(입력이 MusicXML이므로) 항상 실행돼야
    한다.
    """
    if find_musescore_executable() is None:
        pytest.skip(
            "MuseScore 실행 파일을 찾을 수 없습니다. `brew install --cask musescore`로 설치하세요."
        )

    musicxml_path = tmp_path / "score.musicxml"
    _write_synthetic_musicxml(musicxml_path)
    output_pdf = tmp_path / "score.pdf"

    result_path = retypeset_score(musicxml_path, output_pdf)

    assert result_path == output_pdf
    assert output_pdf.is_file()
    with pymupdf.open(output_pdf) as doc:
        assert doc.page_count >= 1


def test_retypeset_score_raises_when_musicxml_missing(tmp_path):
    """존재하지 않는 MusicXML 경로를 주면 mscore를 실행하지 않고 바로 예외를 던져야 한다."""
    missing_musicxml = tmp_path / "missing.musicxml"
    output_pdf = tmp_path / "score.pdf"

    with pytest.raises(FileNotFoundError):
        retypeset_score(missing_musicxml, output_pdf)


def test_retypeset_score_raises_when_musescore_missing(tmp_path, monkeypatch):
    """MuseScore 실행 파일을 찾지 못하면 명확한 예외를 던져야 한다.

    이 머신은 실제로 MuseScore가 설치돼 있으므로, 탐색 함수 자체를 monkeypatch해
    "설치돼 있지 않은 머신"인 것처럼 만들어 이 경로를 검증한다.
    """
    monkeypatch.setattr("app.processors.score.find_musescore_executable", lambda: None)

    musicxml_path = tmp_path / "score.musicxml"
    _write_synthetic_musicxml(musicxml_path)
    output_pdf = tmp_path / "score.pdf"

    with pytest.raises(ScoreRendererUnavailableError):
        retypeset_score(musicxml_path, output_pdf)


def _write_fake_mscore(path, script_body):
    """실제 mscore 대신 쓸 가짜 실행 파일을 만든다(exit 코드/지연 시간을 제어하기 위함)."""
    path.write_text(f"#!/bin/sh\n{script_body}\n")
    path.chmod(0o755)


def test_retypeset_score_does_not_return_stale_pdf_on_later_failure(tmp_path):
    """HIGH 회귀: 같은 output_pdf 경로에 대한 이전 성공 결과를 이후 실패 시 그대로 반환해선 안 된다.

    1차 호출을 실제 MuseScore로 성공시켜 output_pdf에 유효한 PDF를 남긴 뒤,
    같은 경로에 대해 즉시 exit 1만 하는(파일에 손도 대지 않는) 가짜 mscore로
    2차 호출을 하면, stale한 1차 결과를 성공으로 오인하지 않고 실제로
    `ScoreRenderingError`를 던져야 한다.
    """
    if find_musescore_executable() is None:
        pytest.skip(
            "MuseScore 실행 파일을 찾을 수 없습니다. `brew install --cask musescore`로 설치하세요."
        )

    musicxml_path = tmp_path / "score.musicxml"
    _write_synthetic_musicxml(musicxml_path)
    output_pdf = tmp_path / "score.pdf"

    first_result = retypeset_score(musicxml_path, output_pdf)
    assert first_result.is_file()
    assert first_result.stat().st_size > 0

    fake_mscore = tmp_path / "fake_mscore_fail.sh"
    _write_fake_mscore(fake_mscore, "exit 1")

    with pytest.raises(ScoreRenderingError):
        retypeset_score(musicxml_path, output_pdf, mscore_path=fake_mscore)

    assert not output_pdf.exists()


def test_retypeset_score_wraps_timeout_expired(tmp_path):
    """MEDIUM 회귀: mscore가 timeout 내에 끝나지 않으면 원시 TimeoutExpired 대신
    이 모듈의 `ScoreRenderingError`로 감싸 명확한 사유를 전달해야 한다.
    """
    musicxml_path = tmp_path / "score.musicxml"
    _write_synthetic_musicxml(musicxml_path)
    output_pdf = tmp_path / "score.pdf"

    fake_mscore = tmp_path / "fake_mscore_hang.sh"
    _write_fake_mscore(fake_mscore, "sleep 5")

    with pytest.raises(ScoreRenderingError, match="초 내에 끝나지"):
        retypeset_score(musicxml_path, output_pdf, mscore_path=fake_mscore, timeout=0.5)


def test_retypeset_score_logs_stdout_stderr_on_failure(tmp_path, caplog):
    """LOW 회귀: 실패 시 mscore의 stdout/stderr가 로그에 남아야 한다."""
    musicxml_path = tmp_path / "score.musicxml"
    _write_synthetic_musicxml(musicxml_path)
    output_pdf = tmp_path / "score.pdf"

    fake_mscore = tmp_path / "fake_mscore_verbose_fail.sh"
    _write_fake_mscore(
        fake_mscore,
        'echo "stdout marker XYZ"; echo "stderr marker XYZ" >&2; exit 1',
    )

    with caplog.at_level("WARNING", logger="app.processors.score"):
        with pytest.raises(ScoreRenderingError):
            retypeset_score(musicxml_path, output_pdf, mscore_path=fake_mscore)

    assert "stdout marker XYZ" in caplog.text
    assert "stderr marker XYZ" in caplog.text


def test_process_image_connects_recognition_and_retypeset(tmp_path, monkeypatch):
    """SCR-1 + SCR-2 연결: `process_image`가 OMR 인식 후 재조판까지 이어야 한다.

    oemer 체크포인트가 없는 이 머신에서도 연결 자체를 검증할 수 있도록,
    `recognize_score`를 실제 OMR 대신 music21로 만든 유효한 MusicXML을 저장하는
    스텁으로 대체한다(이 테스트의 목적은 OMR 정확도가 아니라 두 단계가 올바른
    순서로 이어지는지 확인하는 것이다).
    """
    if find_musescore_executable() is None:
        pytest.skip(
            "MuseScore 실행 파일을 찾을 수 없습니다. `brew install --cask musescore`로 설치하세요."
        )

    def fake_recognize_score(image, output_musicxml, **kwargs):
        del image, kwargs
        _write_synthetic_musicxml(output_musicxml)
        return output_musicxml

    monkeypatch.setattr("app.processors.score.recognize_score", fake_recognize_score)

    dummy_image = np.full((200, 200, 3), 255, dtype=np.uint8)
    output_pdf = tmp_path / "score.pdf"

    result = process_image(dummy_image, output_pdf)

    assert result.pdf_path == output_pdf
    assert result.musicxml_path.exists()
    assert output_pdf.is_file()
    with pymupdf.open(output_pdf) as doc:
        assert doc.page_count >= 1


def test_retypeset_score_pdf_compatible_with_pdf_assembly(tmp_path):
    """PDF-1 호환성: 재조판 PDF가 `assemble_pdf`로 다른 페이지와 그대로 병합돼야 한다."""
    if find_musescore_executable() is None:
        pytest.skip(
            "MuseScore 실행 파일을 찾을 수 없습니다. `brew install --cask musescore`로 설치하세요."
        )

    from app.pdf_assembly.assemble import assemble_pdf

    musicxml_path = tmp_path / "score.musicxml"
    _write_synthetic_musicxml(musicxml_path)
    score_pdf = retypeset_score(musicxml_path, tmp_path / "score.pdf")

    other_pdf = tmp_path / "other.pdf"
    with pymupdf.open() as blank_doc:
        blank_doc.new_page()
        blank_doc.save(other_pdf)

    merged_pdf = assemble_pdf([other_pdf, score_pdf], tmp_path / "merged.pdf")

    with pymupdf.open(merged_pdf) as merged_doc:
        with pymupdf.open(score_pdf) as score_doc:
            assert merged_doc.page_count == 1 + score_doc.page_count
