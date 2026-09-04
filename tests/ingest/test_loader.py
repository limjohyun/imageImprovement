"""`app/ingest/loader.py`(HEIC/HEIF 입력 지원) 단위 테스트.

핵심 계약: `load_image_bgr`는 어떤 입력(정상/부재/손상)에도 예외를 던지지 않고
OpenCV `np.ndarray`(성공) 또는 `None`(실패)을 반환해야 한다. 이 계약이 깨지면
`app/gui/main_window.py`의 재처리 진입점 3곳(`_on_crop_rotate_clicked` 등)이
try/except 없이 직접 호출하고 있어 Qt 슬롯 밖까지 예외가 전파된다.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.ingest.loader import load_image_bgr


def _make_heic_file(path: Path, *, width: int = 64, height: int = 48) -> np.ndarray:
    """완만한 그라디언트 RGB 이미지를 HEIC로 인코딩해 저장하고, 원본 배열을 반환한다.

    무작위 노이즈는 HEIC 손실 압축과 정반대 특성이라(압축률이 거의 없고
    디코딩 결과가 원본과 크게 달라짐) 왕복 검증에 부적합하므로, 완만한
    그라디언트를 사용해 압축 후에도 원본과 근사하게 유지되도록 한다.
    """
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(0, 255, height, dtype=np.uint8)
    rgb_array = np.zeros((height, width, 3), dtype=np.uint8)
    rgb_array[:, :, 0] = x[np.newaxis, :]
    rgb_array[:, :, 1] = y[:, np.newaxis]
    rgb_array[:, :, 2] = 128
    Image.fromarray(rgb_array, "RGB").save(path, format="HEIF")
    return rgb_array


def test_load_image_bgr_decodes_valid_heic(tmp_path: Path) -> None:
    """정상 HEIC 파일은 원본과 동일한 shape/dtype의 BGR 배열로 디코딩되어야 한다."""
    heic_path = tmp_path / "photo.heic"
    rgb_array = _make_heic_file(heic_path)

    decoded = load_image_bgr(heic_path)

    assert decoded is not None
    assert decoded.dtype == np.uint8
    assert decoded.shape == rgb_array.shape
    # BGR<->RGB 변환만 거치므로 RGB로 되돌리면 원본과 근사해야 한다(HEIC는
    # 손실 압축이라 완전히 동일하지는 않음).
    decoded_rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
    assert np.abs(decoded_rgb.astype(int) - rgb_array.astype(int)).mean() < 5.0


def test_load_image_bgr_returns_none_for_missing_file(tmp_path: Path) -> None:
    """존재하지 않는 경로는 예외 없이 None을 반환해야 한다(cv2.imread와 동일한 관례)."""
    missing_path = tmp_path / "does_not_exist.heic"

    assert load_image_bgr(missing_path) is None


def test_load_image_bgr_returns_none_for_truncated_heic(tmp_path: Path) -> None:
    """손상(잘린) HEIC 파일은 예외를 전파하지 않고 None을 반환해야 한다.

    회귀 테스트: pillow-heif의 C 디코더는 `Image.load()` 시점에 OSError의
    서브클래스가 아닌 순수 ValueError("Unexpected end of file: ...")를 던질 수
    있는데, 예전 구현은 `except OSError`만 잡고 있어 이 예외가 그대로
    전파돼 `load_image_bgr`의 "예외 없이 None 반환" 계약을 깼다.
    """
    good_path = tmp_path / "good.heic"
    _make_heic_file(good_path, width=256, height=192)

    truncated_path = tmp_path / "truncated.heic"
    original_bytes = good_path.read_bytes()
    truncated_path.write_bytes(original_bytes[: len(original_bytes) * 70 // 100])

    # 예외가 나면 pytest가 테스트를 실패로 처리하므로, 이 호출 자체가 곧
    # "예외 없음"에 대한 검증이다.
    assert load_image_bgr(truncated_path) is None


@pytest.mark.parametrize("suffix", [".jpg", ".png"])
def test_load_image_bgr_uses_cv2_for_non_heif_extensions(
    tmp_path: Path, suffix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HEIC/HEIF가 아닌 확장자는 여전히 cv2.imread 경로를 타야 한다."""
    calls: list[str] = []
    original_imread = cv2.imread

    def _tracking_imread(filename: str, *args: object, **kwargs: object) -> np.ndarray | None:
        calls.append(filename)
        return original_imread(filename, *args, **kwargs)

    monkeypatch.setattr(cv2, "imread", _tracking_imread)

    image_path = tmp_path / f"photo{suffix}"
    array = np.random.randint(0, 255, (32, 32, 3), dtype=np.uint8)
    cv2.imwrite(str(image_path), array)

    decoded = load_image_bgr(image_path)

    assert decoded is not None
    assert calls == [str(image_path)]
