"""DIA-1: 도형/그래프 문서 선명화 처리기.

전처리(`app.preprocess`)를 거친 이미지 한 장을 받아 윤곽선을 더 뚜렷하게
다듬은 뒤, 텍스트 레이어 없이 그대로 한 장짜리 PDF로 감싼다. 해상도 자체를
키우는 작업(Real-ESRGAN/고전 업스케일)은 이미 공통 전처리 단계
(`app.preprocess.upscale`)에서 끝났다고 가정하므로, 이 모듈은 "이미 확대된
이미지의 윤곽이 뭉개지지 않도록 다듬는 것"에만 집중한다.

DIA-2(벡터화)와 DIA-3(한계 고지)는 이 태스크 범위 밖이며, 각각 Phase2-3에서
`app.processors.diagram`에 추가되거나 GUI 쪽에서 다뤄질 예정이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import img2pdf
import numpy as np

from app.preprocess.pipeline import PreprocessConfig, run_pipeline

DEFAULT_DPI = 300

# 언샤프 마스킹 기본 파라미터. sigma가 클수록 더 넓은 범위의 대비를 강조하고,
# amount가 클수록 강조 정도가 세진다 — 도형 윤곽선처럼 굵고 뚜렷한 경계에는
# 텍스트보다 다소 넓고 강한 강조가 잘 맞는다(경험적으로 선택한 기본값).
DEFAULT_SHARPEN_SIGMA = 2.0
DEFAULT_SHARPEN_AMOUNT = 1.5

# 업스케일 과정(Lanczos 보간 등)에서 생기는 잔노이즈/링잉을 언샤프 마스킹 전에
# 먼저 정리해야, 노이즈까지 함께 강조되어 윤곽이 오히려 지저분해지는 것을 막는다.
DEFAULT_DENOISE_D = 7
DEFAULT_DENOISE_SIGMA_COLOR = 50
DEFAULT_DENOISE_SIGMA_SPACE = 50


@dataclass
class DiagramResult:
    """도형 처리기가 페이지 한 장을 처리한 결과."""

    sharpened_image: np.ndarray
    """선명화된 이미지 (BGR, uint8). GUI 미리보기 등에 재사용할 수 있도록 함께 반환한다."""

    pdf_path: Path
    """선명화된 이미지를 그대로 담은 한 장짜리 PDF 경로 (DIA-1)."""


def sharpen_diagram(
    image: np.ndarray,
    *,
    sigma: float = DEFAULT_SHARPEN_SIGMA,
    amount: float = DEFAULT_SHARPEN_AMOUNT,
    denoise: bool = True,
) -> np.ndarray:
    """DIA-1: 저해상도에서 확대된 도형 이미지의 윤곽선을 언샤프 마스킹으로 강조한다.

    `denoise=True`(기본값)면 양방향 필터(bilateral filter)로 경계는 보존하면서
    잡음만 먼저 줄인다 — 업스케일 결과에 남은 노이즈를 그대로 언샤프 마스킹하면
    노이즈까지 함께 확대돼 윤곽이 오히려 더 지저분해지기 때문이다.
    """
    if image.size == 0:
        raise ValueError("빈 이미지는 선명화할 수 없습니다.")

    base = (
        cv2.bilateralFilter(
            image,
            DEFAULT_DENOISE_D,
            DEFAULT_DENOISE_SIGMA_COLOR,
            DEFAULT_DENOISE_SIGMA_SPACE,
        )
        if denoise
        else image
    )

    blurred = cv2.GaussianBlur(base, ksize=(0, 0), sigmaX=sigma)
    # 언샤프 마스킹: base + amount * (base - blurred). addWeighted가 결과를
    # uint8 범위로 자동 clip해주므로 별도 클리핑 코드가 필요 없다.
    sharpened = cv2.addWeighted(base, 1.0 + amount, blurred, -amount, 0)
    return sharpened


def _image_to_pdf_bytes(image: np.ndarray, *, dpi: int) -> bytes:
    """이미지를 한 장짜리 PDF 바이트로 감싼다. `text.py`와 동일하게 img2pdf를 사용한다."""
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("이미지를 PNG로 인코딩하는 데 실패했습니다.")
    layout_fun = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
    return img2pdf.convert(encoded.tobytes(), layout_fun=layout_fun)


def build_diagram_pdf(image: np.ndarray, output_pdf: str | Path, *, dpi: int = DEFAULT_DPI) -> Path:
    """선명화된 이미지를 텍스트 레이어 없이 그대로 한 장짜리 PDF로 만든다 (DIA-1).

    도형 문서는 OCR 텍스트 레이어가 필요 없으므로(TXT-2는 텍스트 전용 요구사항),
    OCRmyPDF를 거치지 않고 img2pdf만으로 PDF를 만든다.
    """
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(_image_to_pdf_bytes(image, dpi=dpi))
    return output_pdf


def process_image(
    image: np.ndarray,
    output_pdf: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    sigma: float = DEFAULT_SHARPEN_SIGMA,
    amount: float = DEFAULT_SHARPEN_AMOUNT,
    denoise: bool = True,
) -> DiagramResult:
    """진입점: 전처리 완료된 이미지 한 장 → (선명화된 이미지, 텍스트 레이어 없는 PDF).

    `app.processors.text.process_image`와 동일한 호출 규약(이미지, 출력 경로를
    위치 인자로, 나머지는 키워드 인자로)을 따른다 — `app.router.dispatch`의
    `_PROCESSOR_REGISTRY`가 이 규약을 그대로 호출하기 때문이다(등록 자체는
    Phase2-4 범위).
    """
    sharpened = sharpen_diagram(image, sigma=sigma, amount=amount, denoise=denoise)
    pdf_path = build_diagram_pdf(sharpened, output_pdf, dpi=dpi)
    return DiagramResult(sharpened_image=sharpened, pdf_path=pdf_path)


def process_image_file(
    input_path: str | Path,
    output_pdf: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    sigma: float = DEFAULT_SHARPEN_SIGMA,
    amount: float = DEFAULT_SHARPEN_AMOUNT,
    denoise: bool = True,
    preprocess_config: PreprocessConfig | None = None,
) -> DiagramResult:
    """편의 진입점: 원본 이미지 파일 경로를 받아 공통 전처리부터 한 번에 수행한다."""
    input_path = Path(input_path)
    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {input_path}")
    preprocessed = run_pipeline(image, preprocess_config)
    return process_image(
        preprocessed, output_pdf, dpi=dpi, sigma=sigma, amount=amount, denoise=denoise
    )
