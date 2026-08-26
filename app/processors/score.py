"""SCR-1: 악보 OMR(광학 악보 인식) 처리기.

전처리(`app.preprocess`)를 거친 악보 이미지 한 장을 받아 oemer(사전학습 OMR
모델)로 오선/음표/기호를 인식한 뒤 MusicXML 파일을 생성한다. `oemer.ete.extract`가
파일 경로 기반 CLI 지향 API라서, 이미지를 임시 PNG 파일로 써서 넘긴 뒤 결과
MusicXML을 호출자가 지정한 경로로 복사하는 방식을 쓴다(`text.py`가 img2pdf 호출을
위해 임시 파일 대신 인코딩 바이트를 쓰는 것과 달리, oemer는 경로 자체가 필수
인자라 우회할 수 없다).

재조판 PDF 생성(SCR-2, MuseScore 연동)은 이 모듈의 범위 밖이다 — 여기서는
MusicXML 산출까지만 담당한다.
"""

from __future__ import annotations

import argparse
import logging
import tempfile
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
