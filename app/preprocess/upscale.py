"""PRE-4: 해상도 개선/디노이즈.

기본 진입점(`upscale`)은 사전학습 가중치 없이도 오프라인에서 바로 동작하는
고전적 업스케일(Lanczos 보간 + Non-local-means 디노이즈)을 사용한다.

Real-ESRGAN(`upscale_real_esrgan`)은 별도로 준비해뒀지만 기본 경로에서는 쓰지
않는다 — `realesrgan.RealESRGANer`는 로컬에 `.pth` 가중치 파일이 있어야 동작하고,
없으면 URL에서 자동 다운로드(수십 MB)를 시도하는 구조라 "완전 오프라인" 기본
동작 원칙과 맞지 않기 때문이다. 가중치를 수동으로 내려받아 로컬 경로를 갖고
있는 경우에만 `model_path`를 지정해 이 경로를 사용하면 된다(자세한 내용은
`docs/roadmap.md` Phase1-2 진행 기록 참고).
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def upscale_classical(
    image: np.ndarray, *, scale: float = 2.0, denoise_strength: float = 6.0
) -> np.ndarray:
    """가중치 없이 동작하는 업스케일+디노이즈 폴백.

    Non-local-means로 먼저 노이즈를 줄인 뒤 Lanczos 보간으로 확대한다 — 노이즈가
    있는 채로 확대하면 노이즈까지 함께 커지므로 순서가 중요하다.
    """
    if image.ndim == 3:
        denoised = cv2.fastNlMeansDenoisingColored(
            image,
            None,
            h=denoise_strength,
            hColor=denoise_strength,
            templateWindowSize=7,
            searchWindowSize=21,
        )
    else:
        denoised = cv2.fastNlMeansDenoising(
            image, None, h=denoise_strength, templateWindowSize=7, searchWindowSize=21
        )
    return cv2.resize(denoised, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)


def upscale_real_esrgan(
    image: np.ndarray,
    *,
    model_path: str | Path,
    scale: int = 4,
    tile: int = 0,
) -> np.ndarray:
    """Real-ESRGAN 사전학습 가중치를 이용한 업스케일.

    `model_path`는 로컬에 이미 내려받은 `.pth` 가중치 파일 경로여야 한다(URL을 넘기면
    `realesrgan`이 자동으로 다운로드를 시도하므로, 오프라인 원칙을 지키려면 이 함수를
    호출하는 쪽에서 사전에 파일 존재를 확인하고 명시적으로 로컬 경로만 넘기길 권장한다).
    CPU 추론은 느릴 수 있으므로 큰 이미지는 `tile`을 0보다 크게 지정해 타일 단위로 처리한다.

    주의: `scale`은 `model_path`의 가중치가 실제로 학습된 배율과 반드시 일치해야 한다
    (예: 4배 모델에 `scale=2`를 넘기면 예외 없이 조용히 어긋난 결과가 나올 수 있다).
    """
    # 무거운 ML 의존성(torch/basicsr)은 이 함수를 실제로 호출할 때만 import한다 —
    # 클래식 폴백만 쓰는 경로(기본 파이프라인, 테스트)에서 불필요한 로딩 비용을 피하기 위함.
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Real-ESRGAN 가중치 파일을 찾을 수 없습니다: {model_path}. "
            "미리 로컬에 내려받은 .pth 경로를 지정하세요."
        )

    model = RRDBNet(
        num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=scale
    )
    upsampler = RealESRGANer(scale=scale, model_path=str(model_path), model=model, tile=tile)
    output, _ = upsampler.enhance(image, outscale=scale)
    return output


def upscale(
    image: np.ndarray,
    *,
    scale: float = 2.0,
    model_path: str | Path | None = None,
) -> np.ndarray:
    """PRE-4 진입점.

    `model_path`가 주어지고 실제로 존재하면 Real-ESRGAN을 사용하고, 그렇지 않으면
    (기본 동작) 클래식 폴백을 사용한다. 이렇게 하면 가중치를 아직 준비하지 않은
    상태에서도 파이프라인 전체가 오프라인으로 끝까지 동작한다.
    """
    if model_path is not None and Path(model_path).exists():
        return upscale_real_esrgan(image, model_path=model_path, scale=int(round(scale)))
    if model_path is not None:
        logger.warning(
            "Real-ESRGAN 가중치 경로가 존재하지 않아 클래식 업스케일로 대체합니다: %s", model_path
        )
    return upscale_classical(image, scale=scale)
