"""왜곡된 스마트폰 촬영 사진처럼 보이는 합성 테스트 이미지 생성 유틸리티.

Phase1-2(공통 전처리)부터 이후 모든 Phase의 pytest가 재사용하는 공통 테스트 자산이다.
실제 촬영 사진을 준비하는 대신, PIL/OpenCV로 문서(텍스트/도형/악보)를 렌더링한 뒤
원근 왜곡 + 조명/그림자 + 노이즈 + 저해상도화를 코드로 합성 적용해 "스마트폰으로
삐딱하게 찍은 저화질 사진"처럼 보이게 만든다. pytest 자체에 의존하지 않는 순수
함수/클래스 모음이므로 conftest.py 밖에서도 직접 import해 재사용할 수 있다.

악보 fixture는 손으로 그린 도형이 아니라 music21로 작성한 MusicXML을 실제 엔그레이빙
렌더러(MuseScore)로 렌더링한다 — oemer 같은 사전학습 OMR 모델은 손그림 수준의 가짜
악보를 인식하지 못하기 때문이다. MuseScore는 Phase3 착수 전까지 설치를 미루기로 했으므로,
실행 파일을 찾지 못하면 `ScoreRendererUnavailableError`를 던져 호출자가 pytest.skip 등으로
우아하게 건너뛸 수 있게 한다.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 재현 가능한 테스트를 위한 고정 시드. 특별한 의미는 없고 임의로 고정한 값이다.
DEFAULT_SEED = 20260825


@dataclass
class SyntheticPhoto:
    """합성 촬영 사진 fixture 하나를 표현한다."""

    photo: np.ndarray
    """왜곡(원근/조명/노이즈/저해상도)이 모두 적용된 "촬영된 사진" (BGR, uint8)."""

    ground_truth: np.ndarray
    """왜곡 전 원본 문서 이미지 (정면, 고해상도, BGR). 보정 결과 검증의 기준값으로 쓴다."""

    corners: np.ndarray
    """photo 안에서 문서가 차지하는 4개 모서리 좌표, shape (4, 2) float32.
    순서는 원본 문서의 (좌상, 우상, 우하, 좌하)가 각각 어디로 이동했는지를 그대로 따른다."""

    text: str | None = None
    """텍스트 fixture의 원문(OCR 정확도 비교용). 텍스트 문서가 아니면 None."""


class ScoreRendererUnavailableError(RuntimeError):
    """MuseScore 등 악보 엔그레이빙 렌더러를 찾지 못했을 때 발생시킨다."""


class KoreanFontUnavailableError(RuntimeError):
    """한글 글리프를 지원하는 시스템 폰트를 찾지 못했을 때 발생시킨다."""


# ---------------------------------------------------------------------------
# 공통 왜곡 파이프라인 (텍스트/도형/악보 fixture가 모두 재사용)
# ---------------------------------------------------------------------------


def _make_background(size: tuple[int, int], rng: np.random.Generator) -> np.ndarray:
    """문서 주변 배경(예: 책상 표면)을 흉내내는 저채도 텍스처를 생성한다."""
    height, width = size
    base_color = rng.integers(40, 90, size=3)
    background = np.full((height, width, 3), base_color, dtype=np.uint8)
    texture_noise = rng.normal(0, 8, size=(height, width, 3))
    return np.clip(background.astype(np.float32) + texture_noise, 0, 255).astype(np.uint8)


def _compose_on_background(
    document: np.ndarray, margin_ratio: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """문서 이미지를 더 큰 배경 캔버스 중앙에 배치하고 (캔버스, 문서 모서리 좌표)를 반환한다.

    배경과 문서가 대비되게 만들어야 PRE-1(원근 보정)의 문서 4모서리 자동 검출을
    이후 테스트에서 검증할 수 있다.
    """
    doc_h, doc_w = document.shape[:2]
    margin_x = int(doc_w * margin_ratio)
    margin_y = int(doc_h * margin_ratio)
    canvas_w, canvas_h = doc_w + 2 * margin_x, doc_h + 2 * margin_y
    canvas = _make_background((canvas_h, canvas_w), rng)
    canvas[margin_y : margin_y + doc_h, margin_x : margin_x + doc_w] = document
    corners = np.array(
        [
            [margin_x, margin_y],
            [margin_x + doc_w, margin_y],
            [margin_x + doc_w, margin_y + doc_h],
            [margin_x, margin_y + doc_h],
        ],
        dtype=np.float32,
    )
    return canvas, corners


def _apply_perspective_tilt(
    canvas: np.ndarray,
    doc_corners: np.ndarray,
    max_jitter_ratio: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """캔버스 네 모서리를 무작위로 흔들어 기울어진 촬영을 흉내낸다 (원근 + 회전 동시 발생)."""
    height, width = canvas.shape[:2]
    src = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
    jitter = rng.uniform(-1, 1, size=(4, 2)) * [width * max_jitter_ratio, height * max_jitter_ratio]
    # rng.uniform은 float64를 반환하므로 float32를 요구하는 cv2 API에 맞춰 캐스팅한다.
    dst = (src + jitter).astype(np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)

    background_color = tuple(int(v) for v in canvas[0, 0])
    warped = cv2.warpPerspective(
        canvas,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=background_color,
    )
    warped_corners = cv2.perspectiveTransform(doc_corners.reshape(-1, 1, 2), matrix)
    return warped, warped_corners.reshape(-1, 2)


def _add_lighting_variation(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """대각선 방향의 밝기 그라디언트로 불균일한 조명/그림자를 흉내낸다."""
    height, width = image.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width]
    angle = rng.uniform(0, 2 * np.pi)
    gradient = np.cos(angle) * (xx / width) + np.sin(angle) * (yy / height)
    gradient = (gradient - gradient.min()) / (gradient.max() - gradient.min() + 1e-6)
    strength = rng.uniform(0.35, 0.6)
    factor = 1.0 - strength * gradient
    shaded = image.astype(np.float32) * factor[..., None]
    return np.clip(shaded, 0, 255).astype(np.uint8)


def _add_camera_noise(image: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """저조도 스마트폰 센서 노이즈를 흉내내는 가우시안 노이즈를 추가한다."""
    noise = rng.normal(0, sigma, size=image.shape)
    return np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _downsample(
    image: np.ndarray, corners: np.ndarray, scale: float
) -> tuple[np.ndarray, np.ndarray]:
    """저해상도 촬영을 흉내내기 위해 이미지를 축소한다 (PRE-4 업스케일 보정 테스트용)."""
    height, width = image.shape[:2]
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    small = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
    return small, corners * scale


def _photograph(
    document: np.ndarray,
    *,
    margin_ratio: float = 0.18,
    max_jitter_ratio: float = 0.07,
    noise_sigma: float = 6.0,
    downsample_scale: float = 0.5,
    seed: int = DEFAULT_SEED,
) -> tuple[np.ndarray, np.ndarray]:
    """문서 이미지 한 장에 원근왜곡+조명+노이즈+저해상도화를 합성 적용해 "촬영본"을 만든다."""
    rng = np.random.default_rng(seed)
    canvas, doc_corners = _compose_on_background(document, margin_ratio, rng)
    tilted, tilted_corners = _apply_perspective_tilt(canvas, doc_corners, max_jitter_ratio, rng)
    shaded = _add_lighting_variation(tilted, rng)
    noisy = _add_camera_noise(shaded, noise_sigma, rng)
    photo, final_corners = _downsample(noisy, tilted_corners, downsample_scale)
    return photo, final_corners


# ---------------------------------------------------------------------------
# 텍스트 fixture
# ---------------------------------------------------------------------------

DEFAULT_TEXT_LINES = [
    "Synthetic Fixture Document",
    "The quick brown fox jumps over the lazy dog.",
    "Phase 1 preprocessing pipeline test image.",
    "0123456789 ABCDEFGHIJ abcdefghij",
]

# 한글+영문 혼용(lang="kor+eng") 인식을 검증하기 위한 fixture 문장.
# PIL ImageFont.load_default()는 한글 글리프를 지원하지 않으므로, 이 문장을
# 렌더링할 때는 반드시 시스템에 설치된 한글 지원 폰트(_render_text_document의
# font_path 인자)를 함께 넘겨야 한다.
DEFAULT_KOREAN_TEXT_LINES = [
    "합성 픽스처 문서",
    "빠른 갈색 여우가 게으른 개를 뛰어넘는다.",
    "한글과 영어가 섞인 Phase 1 문서 인식 테스트입니다.",
    "전화번호 010-1234-5678, 우편번호 06236",
]

# macOS에 기본 내장된 한글 지원 폰트 후보 (다른 macOS 머신에서도 최소 하나는
# 있을 가능성이 높은 순서). 전부 없으면 호출자가 pytest.skip으로 건너뛰어야 한다.
_KOREAN_FONT_CANDIDATES = [
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    Path("/System/Library/Fonts/Supplemental/AppleMyungjo.ttf"),
]


def find_korean_font() -> Path | None:
    """한글 글리프를 지원하는 시스템 트루타입 폰트를 찾는다.

    다른 macOS 머신에는 이 폰트들이 없을 수도 있으므로, 예외를 던지지 않고
    None을 반환해 호출자가 pytest.skip 등으로 우아하게 건너뛰게 한다.
    """
    for candidate in _KOREAN_FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _render_text_document(
    lines: list[str] | None = None,
    width: int = 1000,
    height: int = 1300,
    *,
    font_path: Path | None = None,
) -> tuple[np.ndarray, str]:
    """PIL로 흰 배경에 검은 텍스트를 그려 "문서 스캔본"처럼 보이는 이미지를 만든다.

    `font_path`가 주어지면 해당 트루타입 폰트로 렌더링한다 — `ImageFont.load_default()`는
    한글 글리프가 없어 한글 fixture 렌더링에는 쓸 수 없기 때문이다.
    """
    lines = lines if lines is not None else DEFAULT_TEXT_LINES
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = (
        ImageFont.truetype(str(font_path), size=32)
        if font_path
        else ImageFont.load_default(size=32)
    )
    y = 60
    for line in lines:
        draw.text((60, y), line, fill=(0, 0, 0), font=font)
        y += 60
    document = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    return document, "\n".join(lines)


def make_text_photo(
    *,
    seed: int = DEFAULT_SEED,
    lines: list[str] | None = None,
    font_path: Path | None = None,
) -> SyntheticPhoto:
    """스마트폰으로 삐딱하게 찍은 저화질 텍스트 문서 사진 fixture를 생성한다."""
    document, text = _render_text_document(lines, font_path=font_path)
    photo, corners = _photograph(document, seed=seed)
    return SyntheticPhoto(photo=photo, ground_truth=document, corners=corners, text=text)


def make_korean_text_photo(*, seed: int = DEFAULT_SEED) -> SyntheticPhoto:
    """한글+영문이 섞인 텍스트 문서 사진 fixture를 생성한다 (kor+eng OCR 검증용).

    시스템에 한글 지원 폰트가 없으면 `KoreanFontUnavailableError`를 던진다 —
    호출자(테스트)는 이를 pytest.skip으로 처리해 다른 macOS 머신에서도 안전하게
    돌아가게 해야 한다.
    """
    font_path = find_korean_font()
    if font_path is None:
        raise KoreanFontUnavailableError(
            "한글 지원 시스템 폰트를 찾을 수 없습니다 "
            f"(확인한 경로: {[str(p) for p in _KOREAN_FONT_CANDIDATES]})."
        )
    return make_text_photo(seed=seed, lines=DEFAULT_KOREAN_TEXT_LINES, font_path=font_path)


# ---------------------------------------------------------------------------
# 도형 fixture
# ---------------------------------------------------------------------------


def _render_diagram_document(width: int = 1000, height: int = 1300) -> np.ndarray:
    """OpenCV로 사각형/원/선/다각형 등 단순 도형을 그려 "도형 문서"를 흉내낸다."""
    document = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(document, (100, 100), (450, 400), (0, 0, 0), 4)
    cv2.circle(document, (700, 250), 150, (0, 0, 0), 4)
    cv2.line(document, (100, 550), (900, 550), (0, 0, 0), 4)
    cv2.line(document, (100, 550), (900, 1100), (0, 0, 0), 4)
    triangle = np.array([[500, 700], [700, 700], [600, 950]], dtype=np.int32)
    cv2.polylines(document, [triangle], isClosed=True, color=(0, 0, 0), thickness=4)
    return document


def make_diagram_photo(*, seed: int = DEFAULT_SEED) -> SyntheticPhoto:
    """스마트폰으로 삐딱하게 찍은 저화질 도형 문서 사진 fixture를 생성한다."""
    document = _render_diagram_document()
    photo, corners = _photograph(document, seed=seed)
    return SyntheticPhoto(photo=photo, ground_truth=document, corners=corners, text=None)


# ---------------------------------------------------------------------------
# 악보 fixture (music21 + MuseScore 엔그레이빙 렌더링)
# ---------------------------------------------------------------------------


def find_musescore_executable() -> Path | None:
    """MuseScore 4(또는 3) 실행 파일을 찾는다.

    Phase3 착수 전까지는 미설치가 정상 상태이므로 못 찾으면 예외 없이 None을 반환한다.
    """
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


def _build_synthetic_score():
    """oemer 등 사전학습 OMR 모델이 인식 가능한 최소 악보(다장조 8분음표 음계)를 만든다."""
    from music21 import clef, meter, note, stream

    part = stream.Part()
    part.append(clef.TrebleClef())
    part.append(meter.TimeSignature("4/4"))
    for pitch_name in ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]:
        part.append(note.Note(pitch_name, quarterLength=1))
    score = stream.Score()
    score.insert(0, part)
    return score


def _render_score_to_image(mscore_path: Path, tmp_dir: Path) -> np.ndarray:
    """music21 악보를 MusicXML로 내보낸 뒤 MuseScore CLI로 PNG 렌더링한다."""
    score = _build_synthetic_score()
    musicxml_path = tmp_dir / "score.musicxml"
    score.write("musicxml", fp=str(musicxml_path))

    png_path = tmp_dir / "score.png"
    subprocess.run(
        [str(mscore_path), "-o", str(png_path), str(musicxml_path)],
        shell=False,
        check=True,
        capture_output=True,
        timeout=60,
    )

    # MuseScore는 페이지가 1장이어도 파일명에 "-1"을 붙여 내보낸다.
    for candidate in (png_path, png_path.with_name(f"{png_path.stem}-1{png_path.suffix}")):
        if candidate.exists():
            rendered = cv2.imread(str(candidate), cv2.IMREAD_COLOR)
            if rendered is not None:
                return rendered
    raise ScoreRendererUnavailableError(
        f"MuseScore 렌더링 결과 PNG를 찾을 수 없습니다: {png_path}"
    )


def make_score_photo(*, seed: int = DEFAULT_SEED) -> SyntheticPhoto:
    """music21로 작성한 악보를 MuseScore로 렌더링해 촬영본 fixture를 만든다.

    MuseScore 실행 파일을 찾지 못하면 `ScoreRendererUnavailableError`를 던진다 —
    Phase3 착수 전에는 정상 상황이며, 호출자(예: conftest fixture)가 pytest.skip으로
    우아하게 건너뛰도록 설계했다.
    """
    mscore_path = find_musescore_executable()
    if mscore_path is None:
        raise ScoreRendererUnavailableError(
            "MuseScore 실행 파일을 찾을 수 없습니다. Phase3 착수 전이면 정상이며, "
            "`brew install --cask musescore` 설치 후 다시 시도하세요."
        )
    with tempfile.TemporaryDirectory() as tmp:
        document = _render_score_to_image(mscore_path, Path(tmp))
    photo, corners = _photograph(document, seed=seed)
    return SyntheticPhoto(photo=photo, ground_truth=document, corners=corners, text=None)
