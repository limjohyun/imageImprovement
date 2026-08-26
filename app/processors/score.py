"""SCR-1/SCR-2: 악보 OMR(광학 악보 인식) 및 재조판 PDF 생성 처리기.

전처리(`app.preprocess`)를 거친 악보 이미지 한 장을 받아 oemer(사전학습 OMR
모델)로 오선/음표/기호를 인식해 MusicXML 파일을 생성하고(SCR-1),
그 MusicXML을 MuseScore CLI로 재조판해 깔끔한 형태의 PDF로 렌더링한다(SCR-2).
`oemer.ete.extract`가 파일 경로 기반 CLI 지향 API라서, 이미지를 임시 PNG
파일로 써서 넘긴 뒤 결과 MusicXML을 호출자가 지정한 경로로 복사하는 방식을
쓴다(`text.py`가 img2pdf 호출을 위해 임시 파일 대신 인코딩 바이트를 쓰는
것과 달리, oemer는 경로 자체가 필수 인자라 우회할 수 없다).

오류 검수(SCR-3, GUI/외부 편집기 연동)는 이 모듈의 범위 밖이다.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.preprocess.pipeline import PreprocessConfig, run_pipeline

logger = logging.getLogger(__name__)


class ScoreModelUnavailableError(RuntimeError):
    """oemer OMR 체크포인트(.onnx/.h5)가 로컬에 없을 때 발생시킨다.

    체크포인트는 최초 실행 시 `oemer.ete.CHECKPOINTS_URL`에 정의된 GitHub
    Releases URL에서 수백MB 규모로 자동 다운로드되는 구조라, 이 프로젝트의
    "무거운 가중치는 미리 준비되어 있어야 한다" 원칙(Real-ESRGAN과 동일, 참고:
    `app.preprocess.upscale`)에 맞춰 없으면 조용히 다운로드를 트리거하지 않고
    명확한 예외를 던진다. 호출자(테스트 등)는 이를 잡아 우아하게 건너뛰면 된다.
    """


def _checkpoint_path() -> Path:
    """oemer가 1단계 추론에 쓰는 대표 체크포인트 경로. 이 파일 존재 여부로 설치 상태를 판단한다."""
    from oemer import MODULE_PATH

    return Path(MODULE_PATH) / "checkpoints" / "unet_big" / "model.onnx"


def _require_checkpoints() -> None:
    chk_path = _checkpoint_path()
    if not chk_path.exists():
        raise ScoreModelUnavailableError(
            f"oemer OMR 체크포인트를 찾을 수 없습니다: {chk_path}. "
            "`scripts/install_oemer.py` 안내에 따라 oemer를 설치한 뒤, "
            "https://github.com/BreezeWhite/oemer 릴리스에서 제공하는 체크포인트를 "
            "받아 위 경로에 배치하거나(수백MB, 최초 1회) `oemer` CLI를 한 번 실행해 "
            "자동 다운로드를 완료하세요."
        )


def recognize_score(
    image: np.ndarray,
    output_musicxml: str | Path,
    *,
    use_tf: bool = False,
    deskew: bool = True,
) -> Path:
    """SCR-1: 전처리된 악보 이미지를 인식해 MusicXML 파일로 저장한다.

    `deskew=True`(기본값)는 oemer 자체의 오선 곡률 보정(dewarp) 단계를 뜻하며,
    이 프로젝트의 공통 전처리(`app.preprocess`의 원근보정/페이지 단위 deskew)와는
    별개다 — oemer의 dewarp는 촬영 시 종이가 살짝 휘어 오선이 곡선으로 찍힌
    경우를 보정하는 것으로, 페이지 전체의 기울기 보정과는 다른 문제를 다룬다.
    oemer CLI 기본값을 그대로 따라 기본은 켜둔다.
    """
    _require_checkpoints()
    # 체크포인트 확인 전에는 무거운 oemer 서브모듈(onnxruntime 등)을 import하지
    # 않는다 — 체크포인트가 없는 흔한 상태(설치 직후)에서 불필요한 로딩을 피한다.
    from oemer import ete

    output_musicxml = Path(output_musicxml)
    output_musicxml.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        input_image_path = tmp_dir_path / "score_input.png"
        if not cv2.imwrite(str(input_image_path), image):
            raise ValueError("이미지를 PNG로 저장하는 데 실패했습니다.")

        args = argparse.Namespace(
            img_path=str(input_image_path),
            output_path=str(tmp_dir_path),
            use_tf=use_tf,
            save_cache=False,
            without_deskew=not deskew,
        )

        logger.info("oemer OMR 추론을 시작합니다: %s", input_image_path)
        # oemer는 모듈 전역 레이어 저장소(`oemer.layers`)에 중간 결과를 쌓는 구조라,
        # 같은 프로세스에서 여러 번 호출할 때 이전 페이지의 잔여 데이터가 섞이지
        # 않도록 매 호출 전에 반드시 비워야 한다(oemer CLI의 main()도 동일하게 호출).
        ete.clear_data()
        result_path = Path(ete.extract(args))

        output_musicxml.write_bytes(result_path.read_bytes())

    return output_musicxml


def recognize_score_file(
    input_path: str | Path,
    output_musicxml: str | Path,
    *,
    use_tf: bool = False,
    deskew: bool = True,
    preprocess_config: PreprocessConfig | None = None,
) -> Path:
    """편의 진입점: 원본 이미지 파일 경로를 받아 공통 전처리부터 한 번에 수행한다."""
    input_path = Path(input_path)
    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {input_path}")
    preprocessed = run_pipeline(image, preprocess_config)
    return recognize_score(preprocessed, output_musicxml, use_tf=use_tf, deskew=deskew)


# ---------------------------------------------------------------------------
# SCR-2: 재조판 PDF 생성 (MuseScore 연동)
# ---------------------------------------------------------------------------


class ScoreRendererUnavailableError(RuntimeError):
    """MuseScore 실행 파일을 찾지 못했을 때 발생시킨다.

    `tests/fixtures/synthetic.py`의 동명 예외와 역할은 같지만, 프로덕션 코드가
    테스트 코드를 import할 수 없다는 계층 규칙 때문에 이 모듈에 독립적으로 둔다.
    """


class ScoreRenderingError(RuntimeError):
    """MuseScore가 실행은 됐지만 유효한 출력 PDF를 만들지 못했을 때 발생시킨다."""


def find_musescore_executable() -> Path | None:
    """MuseScore 4(또는 3) 실행 파일을 찾는다. 못 찾으면 예외 없이 None을 반환한다."""
    candidates = [
        shutil.which("mscore"),
        shutil.which("mscore4portable"),
        shutil.which("MuseScore4"),
        "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
        "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _musescore_subprocess_env() -> dict[str, str]:
    """MuseScore CLI 호출용 환경변수를 만든다.

    이 프로젝트의 GUI/pytest-qt 테스트는 headless 실행을 위해
    `QT_QPA_PLATFORM=offscreen`을 쓰는데, MuseScore 4가 번들한 Qt는 "offscreen"
    플랫폼 플러그인을 포함하지 않고 "cocoa"만 제공한다. 이 환경변수가 그대로
    상속되면 `mscore` 자식 프로세스가 Qt 플랫폼 플러그인을 찾지 못해 즉시
    크래시한다(`tests/fixtures/synthetic.py`에서 실제 재현 확인, GUI 프로세스와
    MuseScore 자식 프로세스의 Qt 요구사항이 서로 충돌하므로 자식 프로세스
    환경에서만 제거한다).
    """
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    return env


def retypeset_score(
    musicxml_path: str | Path,
    output_pdf: str | Path,
    *,
    mscore_path: str | Path | None = None,
    timeout: float = 120.0,
) -> Path:
    """SCR-2: MusicXML을 MuseScore CLI로 재조판해 깔끔한 형태의 PDF로 렌더링한다.

    이 macOS 환경에서 MuseScore 4는 출력 PDF를 정상적으로 다 쓴 *뒤에* 자체
    크래시 리포터(Crashpad) 종료 경로에서 SIGABRT(exit code 134)로 죽는 경우가
    실제로 재현된다 — 렌더링 자체의 실패가 아니다. 그래서 `check=True`로 종료
    코드만 보고 성공 여부를 판단하지 않고, 실제로 유효한 PDF가 생성됐는지로
    판단한다(`tests/fixtures/synthetic.py`의 `_render_score_to_image`와 동일한
    패턴).
    """
    musicxml_path = Path(musicxml_path)
    if not musicxml_path.is_file():
        raise FileNotFoundError(f"MusicXML 파일을 찾을 수 없습니다: {musicxml_path}")

    resolved_mscore = Path(mscore_path) if mscore_path is not None else find_musescore_executable()
    if resolved_mscore is None:
        raise ScoreRendererUnavailableError(
            "MuseScore 실행 파일을 찾을 수 없습니다. `brew install --cask musescore`로 "
            "설치한 뒤 다시 시도하세요."
        )

    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    # 이번 호출이 output_pdf를 실제로 새로 썼는지를 파일 존재 여부만으로 판단할
    # 수 있도록, mscore 실행 전에 과거 호출이 남긴 파일을 미리 지운다. 이걸
    # 하지 않으면 이번 호출이 완전히 실패(즉시 exit, 파일에 손도 안 댐)해도
    # 이전 호출의 유효한 PDF가 그대로 남아 "성공"으로 오인될 수 있다.
    output_pdf.unlink(missing_ok=True)

    logger.info("MuseScore로 재조판 PDF를 생성합니다: %s -> %s", musicxml_path, output_pdf)
    try:
        result = subprocess.run(
            [str(resolved_mscore), "-o", str(output_pdf), str(musicxml_path)],
            shell=False,
            check=False,
            capture_output=True,
            timeout=timeout,
            env=_musescore_subprocess_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ScoreRenderingError(
            f"MuseScore 렌더링이 {timeout:.0f}초 내에 끝나지 않았습니다: {musicxml_path} "
            "(입력 MusicXML이 손상되었을 가능성이 있습니다)"
        ) from exc

    if not output_pdf.is_file() or output_pdf.stat().st_size == 0:
        stdout = result.stdout.decode("utf-8", errors="replace").strip()[:2000]
        stderr = result.stderr.decode("utf-8", errors="replace").strip()[:2000]
        logger.warning(
            "MuseScore가 유효한 PDF를 생성하지 못했습니다 (exit=%s)\nstdout: %s\nstderr: %s",
            result.returncode,
            stdout,
            stderr,
        )
        raise ScoreRenderingError(
            f"MuseScore가 유효한 재조판 PDF를 생성하지 못했습니다: {output_pdf}"
        )

    return output_pdf


@dataclass
class ScoreResult:
    """SCR-1 + SCR-2를 잇는 진입점(`process_image`/`process_image_file`)의 결과."""

    musicxml_path: Path
    """SCR-1: OMR로 인식한 MusicXML 경로."""

    pdf_path: Path
    """SCR-2: MuseScore로 재조판한 PDF 경로."""


def process_image(
    image: np.ndarray,
    output_pdf: str | Path,
    *,
    output_musicxml: str | Path | None = None,
    use_tf: bool = False,
    deskew: bool = True,
    mscore_path: str | Path | None = None,
) -> ScoreResult:
    """진입점: 전처리 완료된 악보 이미지 한 장 → (MusicXML, 재조판 PDF).

    `app.processors.text.process_image`/`diagram.process_image`와 동일한 호출
    규약(이미지, 출력 PDF 경로를 위치 인자로, 나머지는 키워드 인자로)을
    따른다. `output_musicxml`을 지정하지 않으면 `diagram.py`의 `output_svg`
    기본값 규칙과 동일하게 `output_pdf`와 같은 stem에 `.musicxml` 확장자를
    붙인 경로를 쓴다.

    아직 `app.router.dispatch`의 `_PROCESSOR_REGISTRY`에는 등록하지 않는다
    (Phase3-4 GUI 연결 이후 판단할 사항).
    """
    output_pdf = Path(output_pdf)
    musicxml_target = (
        Path(output_musicxml)
        if output_musicxml is not None
        else output_pdf.with_suffix(".musicxml")
    )

    musicxml_path = recognize_score(image, musicxml_target, use_tf=use_tf, deskew=deskew)
    pdf_path = retypeset_score(musicxml_path, output_pdf, mscore_path=mscore_path)

    return ScoreResult(musicxml_path=musicxml_path, pdf_path=pdf_path)


def process_image_file(
    input_path: str | Path,
    output_pdf: str | Path,
    *,
    output_musicxml: str | Path | None = None,
    use_tf: bool = False,
    deskew: bool = True,
    mscore_path: str | Path | None = None,
    preprocess_config: PreprocessConfig | None = None,
) -> ScoreResult:
    """편의 진입점: 원본 이미지 파일 경로를 받아 공통 전처리부터 한 번에 수행한다."""
    input_path = Path(input_path)
    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {input_path}")
    preprocessed = run_pipeline(image, preprocess_config)
    return process_image(
        preprocessed,
        output_pdf,
        output_musicxml=output_musicxml,
        use_tf=use_tf,
        deskew=deskew,
        mscore_path=mscore_path,
    )
