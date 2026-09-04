"""이미지 입력 로딩을 한 곳에서 처리한다 (app/ingest, CLAUDE.md 아키텍처 참고).

지금까지 GUI(`app/gui/main_window.py`의 자르기/회전/원근보정 재처리 진입점 3곳,
`app/gui/worker.py`의 배치 처리 진입점 1곳)가 `cv2.imread(str(path))`를 직접
중복 호출해왔는데, OpenCV는 아이폰 기본 카메라 저장 포맷인 HEIC/HEIF를
네이티브로 디코딩하지 못해 `cv2.imread`가 조용히 `None`을 반환한다. 이 모듈은
그 로딩 지점을 하나로 모아 확장자에 따라 적절한 디코더(OpenCV 또는
pillow-heif)로 분기하고, 항상 OpenCV와 동일한 BGR `np.ndarray`를 반환한다.

실패 시 동작은 기존 `cv2.imread` 호출부들의 관례를 그대로 따른다: 예외를
던지지 않고 `None`을 반환한다. 호출부는 이미 `if raw_image is None: ...`
패턴으로 사용자에게 에러를 안내하고 있으므로, 이 모듈에서 새로운 예외 타입을
만들어 그 관례를 깨지 않는다.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# HEIC/HEIF를 PIL.Image.open()이 인식하도록 등록한다. 모듈 임포트 시 한 번만
# 등록하면 되고, 여러 번 호출해도 안전하다(pillow-heif 자체가 idempotent하게
# 구현되어 있음).
pillow_heif.register_heif_opener()

_HEIF_EXTENSIONS = {".heic", ".heif"}


def load_image_bgr(path: str | Path) -> np.ndarray | None:
    """이미지 파일을 OpenCV 호환 BGR `np.ndarray`로 읽는다.

    `.heic`/`.heif`는 pillow-heif로 디코딩하고, 그 외 확장자는 기존과 동일하게
    `cv2.imread`로 읽는다. 실패(파일 없음, 손상, 미지원 포맷)하면 `None`을
    반환한다.
    """
    path = Path(path)
    if path.suffix.lower() in _HEIF_EXTENSIONS:
        return _load_heif_as_bgr(path)
    return cv2.imread(str(path))


def _load_heif_as_bgr(path: Path) -> np.ndarray | None:
    """HEIC/HEIF 파일을 Pillow(+pillow-heif)로 디코딩해 BGR 배열로 변환한다."""
    try:
        image = Image.open(path)
        image.load()
    except (OSError, ValueError, EOFError):
        # 파일 없음(FileNotFoundError)·미지원 포맷(UnidentifiedImageError)은
        # OSError 계열이지만, 손상되거나 잘린(truncated) HEIC 파일은
        # pillow-heif의 C 디코더가 `image.load()` 시점에 OSError의
        # 서브클래스가 아닌 순수 ValueError(예: "Unexpected end of file")나
        # EOFError를 던질 수 있다. 이 모듈은 "실패 시 예외를 던지지 않고
        # None을 반환한다"는 계약을 스스로 문서화하고 있으므로, 발생 가능한
        # 예외 타입을 모두 여기서 잡아 cv2.imread와 동일하게 None을 반환해
        # 호출부(app/gui/main_window.py의 재처리 진입점 등)가 기존 관례대로
        # try/except 없이 호출해도 예외가 새어나가지 않게 한다.
        logger.exception("HEIC/HEIF 이미지를 읽을 수 없습니다: %s", path)
        return None

    # 아이폰 HEIC 사진은 EXIF Orientation 태그가 흔해서, 반영하지 않으면
    # 회전된 이미지가 그대로 파이프라인(PRE-1 원근보정/PRE-2 deskew)에 들어가
    # 혼란을 준다. pillow-heif는 대부분 디코딩 시점에 이미 방향을 반영하지만,
    # 그렇지 않은 경우를 대비해 방어적으로 한 번 더 적용한다(이미 반영된
    # 경우엔 EXIF Orientation이 1로 재설정돼 있어 아무 효과가 없는 안전한
    # no-op이다).
    transposed = ImageOps.exif_transpose(image)
    if transposed is None:
        return None

    rgb_array = np.asarray(transposed.convert("RGB"))
    return cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
