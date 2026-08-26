"""oemer(Phase3 OMR 라이브러리) 설치 스크립트.

`oemer==0.1.8`은 PyPI 메타데이터상 `onnxruntime-gpu`를 하드 의존성으로 선언하는데,
이 패키지는 macOS(Darwin)용 배포판이 PyPI에 전혀 없어 `pip install oemer`를 그대로
실행하면 이 머신에서 다음과 같이 실패한다(실제 재현 확인함):

    ERROR: No matching distribution found for onnxruntime-gpu

oemer 코드 자체는 `import onnxruntime`만 하고 GPU 전용 API를 강제하지 않으므로,
CPU 전용 `onnxruntime`을 먼저 정상 설치해두고(이는 `pyproject.toml`의 일반
dependencies가 책임진다) `oemer` 자체는 `--no-deps`로 설치해 문제가 되는 의존성
해석 단계를 아예 건너뛰는 방식으로 우회한다. 이 우회가 `pyproject.toml`의 일반
dependencies 목록에 `oemer`를 그냥 추가하는 방식으로는 불가능하기 때문에(`pip
install -e ".[dev]"`가 oemer의 선언된 메타데이터를 그대로 resolve하려다 다시
실패한다), `scripts/patch_basicsr.py`와 같은 후속 설치 스크립트 형태로 분리했다.

venv를 재생성한 뒤 아래 순서로 실행한다(먼저 `pip install -e ".[dev]"`로
onnxruntime/scikit-learn/typing-extensions 등 정상 의존성을 설치해둔 다음 실행):

    .venv/bin/python scripts/install_oemer.py

이미 올바른 버전이 설치되어 있으면 아무 작업도 하지 않는다(idempotent).
"""

from __future__ import annotations

import logging
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OEMER_VERSION = "0.1.8"


def _installed_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def install_oemer() -> None:
    """`oemer==0.1.8`을 `--no-deps`로 설치한다.

    onnxruntime 자체는 이 스크립트가 아니라 `pyproject.toml`의 일반 dependencies가
    설치하므로, 여기서는 oemer가 정상적으로 import 가능한 상태를 만드는 마지막
    한 조각만 담당한다. 없으면 명확히 경고만 남기고 계속 진행한다(설치 순서를
    지키지 않은 사용자에게 원인을 알려주는 용도일 뿐, 이 스크립트 자체의 책임은
    아니다).
    """
    if _installed_version("onnxruntime") is None:
        logger.warning(
            "onnxruntime이 설치되어 있지 않습니다. 먼저 "
            "`.venv/bin/python -m pip install -e \".[dev]\"`로 정상 의존성을 설치한 "
            "뒤 이 스크립트를 다시 실행하세요."
        )

    current = _installed_version("oemer")
    if current == OEMER_VERSION:
        logger.info("oemer==%s가 이미 설치되어 있습니다.", OEMER_VERSION)
        return

    logger.info(
        "oemer==%s를 --no-deps로 설치합니다 "
        "(macOS용 onnxruntime-gpu 배포판이 PyPI에 없어 일반 설치가 실패하기 때문).",
        OEMER_VERSION,
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", f"oemer=={OEMER_VERSION}", "--no-deps"],
        check=True,
    )
    logger.info(
        "oemer==%s 설치 완료. OMR 체크포인트(.onnx/.h5, 수백MB)는 최초 실행 시 "
        "자동 다운로드되거나 https://github.com/BreezeWhite/oemer 릴리스에서 "
        "수동으로 받아야 합니다(자세한 내용은 README.md 참고).",
        OEMER_VERSION,
    )


if __name__ == "__main__":
    install_oemer()
