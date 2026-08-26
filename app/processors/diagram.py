"""DIA-1: 도형/그래프 문서 선명화 처리기.

전처리(`app.preprocess`)를 거친 이미지 한 장을 받아 윤곽선을 더 뚜렷하게
다듬은 뒤, 텍스트 레이어 없이 그대로 한 장짜리 PDF로 감싼다. 해상도 자체를
키우는 작업(Real-ESRGAN/고전 업스케일)은 이미 공통 전처리 단계
(`app.preprocess.upscale`)에서 끝났다고 가정하므로, 이 모듈은 "이미 확대된
이미지의 윤곽이 뭉개지지 않도록 다듬는 것"에만 집중한다.

DIA-2(벡터화)는 사용자가 명시적으로 요청했을 때만 실행되는 별도 옵션으로
`vectorize_diagram`/`process_image(vectorize=True)`에 구현되어 있다. DIA-3(한계
고지)는 GUI 위젯 자체는 Phase2-4 범위이므로, 여기서는 벡터화 결과에 포함할
고지 문구(`VECTORIZATION_DISCLAIMER`)만 준비해 `DiagramResult`를 통해 전달한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import img2pdf
import numpy as np
import vtracer

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

# vtracer 기본 파라미터. "stacked" 계층 모드 + "spline" 곡선 모드는 사진에서
# 흔한 매끄러운 도형 윤곽(원, 곡선 화살표 등)을 각진 폴리곤보다 자연스럽게
# 재현하는 vtracer 공식 예제 기본값과 동일하다.
DEFAULT_VTRACER_COLOR_MODE = "color"
DEFAULT_VTRACER_HIERARCHICAL = "stacked"
DEFAULT_VTRACER_MODE = "spline"
DEFAULT_VTRACER_FILTER_SPECKLE = 4
DEFAULT_VTRACER_COLOR_PRECISION = 6
DEFAULT_VTRACER_LAYER_DIFFERENCE = 16
DEFAULT_VTRACER_CORNER_THRESHOLD = 60
DEFAULT_VTRACER_LENGTH_THRESHOLD = 4.0
DEFAULT_VTRACER_MAX_ITERATIONS = 10
DEFAULT_VTRACER_SPLICE_THRESHOLD = 45
DEFAULT_VTRACER_PATH_PRECISION = 8

# DIA-3: 벡터화 결과에 항상 동반되는 한계 고지 문구. Phase2-4에서 GUI가 이
# 문구를 그대로 가져다 사용자에게 보여줄 수 있도록 처리기 계층에 준비해둔다
# (docs/prd.md §3 "PPT 도형의 완전한 재편집(PPTX 생성)"은 논-목표).
VECTORIZATION_DISCLAIMER = (
    "이 SVG는 이미지 윤곽선을 추적(트레이싱)한 벡터일 뿐, PowerPoint(PPTX)에서 "
    "원본처럼 완전히 재편집 가능한 도형 객체가 아닙니다. 선/색상 정도의 제한된 "
    "편집만 가능하며, 텍스트 상자나 개별 도형 단위의 편집은 지원하지 않습니다."
)


@dataclass
class DiagramResult:
    """도형 처리기가 페이지 한 장을 처리한 결과."""

    sharpened_image: np.ndarray
    """선명화된 이미지 (BGR, uint8). GUI 미리보기 등에 재사용할 수 있도록 함께 반환한다."""

    pdf_path: Path
    """선명화된 이미지를 그대로 담은 한 장짜리 PDF 경로 (DIA-1)."""

    svg_path: Path | None = None
    """DIA-2: 벡터화를 명시적으로 요청했을 때만 채워지는 SVG 결과 경로.
    기본값 None은 "벡터화를 수행하지 않았음"을 뜻한다."""

    vectorization_disclaimer: str | None = None
    """DIA-3: `svg_path`가 채워졌을 때만 함께 채워지는 한계 고지 문구.
    GUI는 이 필드가 None이 아니면 그대로 사용자에게 노출해야 한다."""


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


def vectorize_diagram(
    image: np.ndarray,
    output_svg: str | Path,
    *,
    color_mode: str = DEFAULT_VTRACER_COLOR_MODE,
    hierarchical: str = DEFAULT_VTRACER_HIERARCHICAL,
    mode: str = DEFAULT_VTRACER_MODE,
    filter_speckle: int = DEFAULT_VTRACER_FILTER_SPECKLE,
    color_precision: int = DEFAULT_VTRACER_COLOR_PRECISION,
    layer_difference: int = DEFAULT_VTRACER_LAYER_DIFFERENCE,
    corner_threshold: int = DEFAULT_VTRACER_CORNER_THRESHOLD,
    length_threshold: float = DEFAULT_VTRACER_LENGTH_THRESHOLD,
    max_iterations: int = DEFAULT_VTRACER_MAX_ITERATIONS,
    splice_threshold: int = DEFAULT_VTRACER_SPLICE_THRESHOLD,
    path_precision: int = DEFAULT_VTRACER_PATH_PRECISION,
) -> Path:
    """DIA-2: 선명화된 이미지를 SVG 벡터로 변환한다.

    기본 파이프라인에 자동 포함되지 않고 사용자가 명시적으로 요청했을 때만
    호출되는 별도 함수다 (`process_image(vectorize=True)` 참고). vtracer는
    파일 경로뿐 아니라 이미지 바이트를 직접 받는 `convert_raw_image_to_svg`도
    제공하므로, `_image_to_pdf_bytes`와 마찬가지로 `cv2.imencode`로 인코딩한
    바이트를 그대로 넘겨 임시 파일 없이 변환한다.
    """
    if image.size == 0:
        raise ValueError("빈 이미지는 벡터화할 수 없습니다.")

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("이미지를 PNG로 인코딩하는 데 실패했습니다.")

    svg_content = vtracer.convert_raw_image_to_svg(
        encoded.tobytes(),
        img_format="png",
        colormode=color_mode,
        hierarchical=hierarchical,
        mode=mode,
        filter_speckle=filter_speckle,
        color_precision=color_precision,
        layer_difference=layer_difference,
        corner_threshold=corner_threshold,
        length_threshold=length_threshold,
        max_iterations=max_iterations,
        splice_threshold=splice_threshold,
        path_precision=path_precision,
    )

    output_svg = Path(output_svg)
    output_svg.parent.mkdir(parents=True, exist_ok=True)
    output_svg.write_text(svg_content, encoding="utf-8")
    return output_svg


def process_image(
    image: np.ndarray,
    output_pdf: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    sigma: float = DEFAULT_SHARPEN_SIGMA,
    amount: float = DEFAULT_SHARPEN_AMOUNT,
    denoise: bool = True,
    vectorize: bool = False,
    output_svg: str | Path | None = None,
) -> DiagramResult:
    """진입점: 전처리 완료된 이미지 한 장 → (선명화된 이미지, 텍스트 레이어 없는 PDF).

    `app.processors.text.process_image`와 동일한 호출 규약(이미지, 출력 경로를
    위치 인자로, 나머지는 키워드 인자로)을 따른다 — `app.router.dispatch`의
    `_PROCESSOR_REGISTRY`가 이 규약을 그대로 호출하기 때문이다(등록 자체는
    Phase2-4 범위).

    `vectorize=False`(기본값)면 DIA-2 벡터화는 전혀 실행되지 않는다 — PRD가
    벡터화를 "사용자가 요청 시"로 명시했으므로, 모든 도형 문서에 강제로 SVG를
    만들지 않는다. `vectorize=True`일 때만 SVG를 만들고, 그 결과에 DIA-3 한계
    고지 문구를 함께 채워 반환한다.
    """
    sharpened = sharpen_diagram(image, sigma=sigma, amount=amount, denoise=denoise)
    pdf_path = build_diagram_pdf(sharpened, output_pdf, dpi=dpi)

    svg_path: Path | None = None
    disclaimer: str | None = None
    if vectorize:
        svg_target = Path(output_svg) if output_svg is not None else Path(output_pdf).with_suffix(
            ".svg"
        )
        svg_path = vectorize_diagram(sharpened, svg_target)
        disclaimer = VECTORIZATION_DISCLAIMER

    return DiagramResult(
        sharpened_image=sharpened,
        pdf_path=pdf_path,
        svg_path=svg_path,
        vectorization_disclaimer=disclaimer,
    )


def process_image_file(
    input_path: str | Path,
    output_pdf: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    sigma: float = DEFAULT_SHARPEN_SIGMA,
    amount: float = DEFAULT_SHARPEN_AMOUNT,
    denoise: bool = True,
    vectorize: bool = False,
    output_svg: str | Path | None = None,
    preprocess_config: PreprocessConfig | None = None,
) -> DiagramResult:
    """편의 진입점: 원본 이미지 파일 경로를 받아 공통 전처리부터 한 번에 수행한다."""
    input_path = Path(input_path)
    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {input_path}")
    preprocessed = run_pipeline(image, preprocess_config)
    return process_image(
        preprocessed,
        output_pdf,
        dpi=dpi,
        sigma=sigma,
        amount=amount,
        denoise=denoise,
        vectorize=vectorize,
        output_svg=output_svg,
    )
