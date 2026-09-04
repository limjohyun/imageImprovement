"""Phase1-5(GUI-1,2,4)+Phase2-4(DIA-3 UI)+Phase3-4(SCR-3 UI): 파이프라인 전체를 백그라운드
스레드에서 실행하는 워커.

전처리(`app.preprocess`) + 라우팅(`app.router`) + 처리기(`app.processors.*`) +
PDF 병합(`app.pdf_assembly`)은 모두 무거운 연산(업스케일, Tesseract, OCRmyPDF/
Ghostscript 서브프로세스 호출, vtracer, oemer/MuseScore 등)이므로 GUI 메인
스레드에서 그대로 호출하면 UI가 블로킹된다. `QThread`를 상속해 이 전체 과정을
별도 스레드에서 실행한다.

`ProcessingWorker`는 이미지 목록을 순회하며 각 페이지를 자동 분류(`DocumentType`)한
뒤 알맞은 처리기(텍스트/도형/악보)로 위임한다(최초 배치 처리는 항상 자동 분류).
`VectorizeWorker`는 이미 도형으로 처리된 페이지 한 장에 대해 사용자가 명시적으로
"SVG로 벡터화"를 요청했을 때만 별도로 실행되는 훨씬 가벼운 워커다(DIA-2).

악보 페이지의 오류 검수(SCR-3, "MuseScore에서 열기")는 `subprocess.Popen`으로 이미
비블로킹이라 `VectorizeWorker` 같은 별도 QThread가 필요 없다 — 호출부(`MainWindow`)가
`app.processors.score.open_score_in_external_editor`를 직접 호출하면 된다.

QThread가 기본 제공하는 `finished` 시그널(인자 없음)을 그대로 사용한다 — 이 시그널을
커스텀 시그널로 덮어쓰면 pytest-qt 공식 예제(`qtbot.waitSignal(worker.finished, ...)`,
https://pytest-qt.readthedocs.io/en/latest/signals.html)가 기대하는 스레드 종료 알림
메커니즘과 이름이 충돌한다. 처리 실패는 별도 시그널(`error_occurred`)로 전달하고,
결과 값(성공 시 병합 PDF 경로 포함)은 스레드 종료 후에도 읽을 수 있도록 인스턴스
속성(`merged_pdf_path`, `page_results`, `svg_path`)에 남겨둔다. `finished` 시그널을
받은 뒤 호출부가 해당 속성을 직접 읽으면 되므로 별도의 결과 전달용 시그널은 두지 않는다.

배치 중 한 페이지가 (예: 줄무늬 배경이 오선으로 오검출되어 `SCORE`로 잘못 분류되거나,
악보로 정확히 분류됐지만 oemer OMR 체크포인트가 로컬에 없어 `ScoreModelUnavailableError`가
나는 등) 어떤 이유로든 처리에 실패하더라도, 그 한 장 때문에 이미 성공한 나머지 페이지
결과까지 버리지 않는다 — 페이지 단위 실패는 `failed_pages`에 모으고 계속 진행하며,
성공한 페이지가 하나라도 있으면 그것만으로 병합 PDF를 만든다.

Phase4-1(GUI-3 일부, 자르기/회전): `_process_one`이 하던 "전처리 → 자동 분류 →
라우팅 → PageResult 변환" 로직을 모듈 함수 `process_page_image()`로 뽑아
`ProcessingWorker`와 `ReprocessWorker`가 함께 재사용한다. 자르기/회전은 이미
PRE-1~5 전처리를 거친 결과물이 아니라 원본 raw 사진에 적용해야 정확하므로(그렇지
않으면 이미 원근 보정된 이미지를 다시 자르는 문제가 생긴다), 호출부(`MainWindow`)가
raw 이미지를 읽어 `app.preprocess.manual_correction.apply_manual_correction`으로
자르기/회전까지 마친 배열을 만든 뒤 `ReprocessWorker`에 넘기면, 그 지점부터
`process_page_image()`로 파이프라인 전체를 다시 태운다.

Phase4-4(RT-1,2 고도화): `process_page_image()`와 `ReprocessWorker`에 `type_override`
키워드 인자를 추가해, GUI에서 사용자가 문서 유형을 수동으로 지정했을 때(RT-1의
"수동 오버라이드") `classify_document_type(..., override=type_override)`로 그대로
전달한다. `ProcessingWorker`(최초 배치 처리)는 계속 자동 분류만 사용하고, 수동
오버라이드는 이미 한 번 처리된 페이지를 다시 처리하는 `ReprocessWorker` 경로에서만
쓰인다 — 자르기/회전(Phase4-1)과 동일한 "재처리" 개념이기 때문이다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal

from app.ingest import load_image_bgr
from app.pdf_assembly.assemble import assemble_pdf
from app.preprocess.pipeline import PreprocessConfig, run_pipeline
from app.processors.diagram import DiagramResult
from app.processors.diagram import vectorize_diagram as _vectorize_diagram
from app.processors.score import ScoreResult
from app.processors.text import TextOcrResult
from app.router.classifier import DocumentType, classify_document_type
from app.router.dispatch import UnsupportedDocumentTypeError, route_and_process

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """입력 이미지 한 장을 처리한 결과.

    `input_path`/`page_pdf_path`/`text` 세 필드는 Phase1부터 있던 필드로, 기존
    호출부(테스트 포함)가 키워드 인자로 직접 `PageResult(...)`를 생성하고 있어
    이름과 호출 방식을 바꾸지 않는다. Phase2-4/Phase3-4에서 추가된 필드는 모두
    기본값이 있는 키워드 전용 확장이다.
    """

    input_path: Path
    page_pdf_path: Path
    text: str | None = None
    """OCR 인식 텍스트 (TXT-1/TXT-3). 도형 페이지는 텍스트 레이어가 없으므로 None."""

    document_type: DocumentType = DocumentType.TEXT
    """RT-1 자동 분류 결과. GUI가 이 값으로 검수 패널/벡터화 버튼 활성 여부를 정한다."""

    sharpened_image: np.ndarray | None = None
    """도형 페이지의 선명화된 이미지 (BGR, uint8). DIA-2 벡터화를 재전처리 없이
    재사용할 수 있도록 보관한다. 텍스트 페이지는 None."""

    svg_path: Path | None = None
    """DIA-2: 사용자가 명시적으로 벡터화를 요청했을 때만 채워지는 SVG 결과 경로."""

    vectorization_disclaimer: str | None = None
    """DIA-3: `svg_path`가 채워졌을 때만 함께 채워지는 한계 고지 문구."""

    musicxml_path: Path | None = None
    """SCR-3: 악보로 분류된 페이지에서만 채워지는 OMR 인식 MusicXML 경로.
    "MuseScore에서 열기" 버튼이 이 값으로 외부 편집기를 연다."""

    crop_rect: tuple[int, int, int, int] | None = None
    """Phase4-1(GUI-3): 사용자가 지정한 자르기 영역 `(x, y, width, height)`
    (회전 후 이미지 기준). `CropRotateDialog`를 다시 열 때 이전 값을 기본값으로
    보여주기 위해 보관한다. 자르기를 적용하지 않았으면 None."""

    rotation_degrees: int = 0
    """Phase4-1(GUI-3): 사용자가 지정한 회전 각도(90도 단위, 0/90/180/270)."""

    type_override: DocumentType | None = None
    """Phase4-4(RT-1 수동 오버라이드): 사용자가 문서 유형을 직접 지정했으면 그 값,
    자동 분류를 그대로 썼으면 None. `crop_rect`/`rotation_degrees`와 마찬가지로
    다음 재처리 요청에서도 이전 선택을 이어가기 위해 보관한다."""

    corners: np.ndarray | None = None
    """PRE-1(GUI 수동 오버라이드): 사용자가 원근 보정 4모서리 좌표를 직접 지정했으면
    그 값(shape (4, 2)), 자동 검출을 그대로 썼으면 None. `crop_rect`/`rotation_degrees`/
    `type_override`와 마찬가지로 다음 재처리 요청(자르기/회전, 문서 유형 변경 등)에서도
    이전에 지정한 수동 코너가 조용히 사라지지 않도록 보관한다. `process_page_image()`는
    이 값을 채우지 않는다(자르기/회전과 마찬가지로 호출부인 `MainWindow`가 재처리 완료
    후 원래 요청에 쓰인 값을 그대로 다시 기록한다).

    한계: 이 좌표는 그것이 지정됐던 당시 이미지 크기 기준이다. 이후 자르기/회전으로
    이미지 크기가 달라지면 더 이상 유효하지 않으므로(범위 밖 좌표로 원근 변환하면
    `cv2.warpPerspective`가 예외 없이 대부분 검은색인 손상된 이미지를 만들어낸다),
    `MainWindow._preprocess_config_for_corners()`가 재처리 시점의 실제 이미지 크기와
    비교해 범위를 벗어나면 이 값을 폐기하고 자동 검출로 되돌린다 — 이 경우 이
    필드는 다음 `PageResult`에 `None`으로 다시 기록된다."""


def process_page_image(
    image: np.ndarray,
    input_path: Path,
    page_pdf_path: Path,
    *,
    lang_kwargs: dict[str, str] | None = None,
    preprocess_config: PreprocessConfig | None = None,
    type_override: DocumentType | None = None,
) -> PageResult:
    """이미지 한 장을 (공통 전처리 → 자동 분류 → 위임 → `PageResult` 변환)까지 처리한다.

    `ProcessingWorker`(최초 배치 처리)와 `ReprocessWorker`(Phase4-1: 자르기/회전
    보정 후 재처리)가 이 함수를 공유한다 — 이미 메모리에 올라온 이미지 배열을
    받는 것이 계약이므로, 파일을 새로 읽어오는 책임은 호출자에게 있다(배치
    최초 처리는 원본 파일에서, 재처리는 사용자가 보정한 배열에서 시작하기 때문에
    "이미지를 어디서 가져오는지"가 다르다).

    `route_and_process`는 이미 전처리된 이미지를 받는 API이므로, 여기서 전처리를
    먼저 한 번만 수행하고 그 결과를 넘긴다(이중 전처리 방지). 분류는 여기서 먼저
    한 번 수행해(`classify_document_type`) 그 결과에 따라 텍스트 처리기 전용
    옵션(`lang`)이 도형/악보 처리기에 잘못 전달되지 않게 한다.

    `type_override`(Phase4-4, RT-1 수동 오버라이드): GUI에서 사용자가 문서 유형을
    직접 지정했을 때 자동 분류를 건너뛰고 그 유형을 그대로 쓴다. `None`이면 기존과
    동일하게 자동 분류(`classify_document_type`)에 맡긴다.
    """
    lang_kwargs = lang_kwargs or {}
    preprocessed = run_pipeline(image, preprocess_config)

    document_type = classify_document_type(preprocessed, override=type_override)
    extra_kwargs = lang_kwargs if document_type == DocumentType.TEXT else {}
    result = route_and_process(preprocessed, page_pdf_path, override=document_type, **extra_kwargs)

    if isinstance(result, TextOcrResult):
        return PageResult(
            input_path=input_path,
            page_pdf_path=result.pdf_path,
            text=result.text,
            document_type=document_type,
        )
    if isinstance(result, DiagramResult):
        return PageResult(
            input_path=input_path,
            page_pdf_path=result.pdf_path,
            text=None,
            document_type=document_type,
            sharpened_image=result.sharpened_image,
            svg_path=result.svg_path,
            vectorization_disclaimer=result.vectorization_disclaimer,
        )
    if isinstance(result, ScoreResult):
        return PageResult(
            input_path=input_path,
            page_pdf_path=result.pdf_path,
            text=None,
            document_type=document_type,
            musicxml_path=result.musicxml_path,
        )
    # route_and_process가 미구현 유형에 대해서는 이미 UnsupportedDocumentTypeError를
    # 던지므로 정상 흐름에서는 도달하지 않는다. 향후 새 처리기가 등록됐는데 여기
    # 변환 로직을 깜빡 잊는 실수를 조용히 넘기지 않기 위한 안전망이다.
    raise UnsupportedDocumentTypeError(
        f"'{document_type.value}' 처리 결과를 PageResult로 변환할 방법이 없습니다."
    )


class ProcessingWorker(QThread):
    """선택된 이미지 파일들을 순회하며 자동 분류 후 알맞은 처리기로 위임하고 최종 PDF로 병합한다."""

    progress_changed = Signal(int, int)
    """(완료한 페이지 수, 전체 페이지 수)."""

    page_processed = Signal(object)
    """페이지 한 장 처리가 끝날 때마다 `PageResult`를 실어 보낸다(미리보기 갱신용)."""

    error_occurred = Signal(str)
    """파이프라인 도중 예외가 발생했을 때(또는 일부 페이지가 실패했을 때) 사용자에게
    보여줄 메시지. 전체 실패든 일부 페이지 실패든 이 시그널 하나로 알린다 — 구분은
    호출부가 `merged_pdf_path`가 채워졌는지로 판단한다."""

    def __init__(
        self,
        image_paths: list[Path],
        work_dir: Path,
        *,
        lang: str | None = None,
        preprocess_config: PreprocessConfig | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.image_paths = [Path(p) for p in image_paths]
        self.work_dir = Path(work_dir)
        self._lang_kwargs = {"lang": lang} if lang else {}
        self._preprocess_config = preprocess_config
        self.page_results: list[PageResult] = []
        self.failed_pages: list[tuple[Path, str]] = []
        """페이지 단위로 실패한 (입력 경로, 오류 메시지) 목록. 배치 중 일부 페이지만
        (예: 분류 오탐으로 미구현 유형에 배정) 실패해도 나머지 페이지는 계속
        처리하고 병합할 수 있도록, 예외를 즉시 던지는 대신 여기 모아둔다."""
        self.merged_pdf_path: Path | None = None

    def run(self) -> None:
        """QThread 진입점.

        페이지 하나 처리 실패는 배치 전체를 중단시키지 않는다 — 실패한 페이지는
        `failed_pages`에 기록하고 다음 페이지로 넘어간다. 성공한 페이지가 하나라도
        있으면 그 페이지들만으로 병합 PDF를 만들어 `merged_pdf_path`를 채우고,
        실패가 있었다면 `error_occurred`로 요약을 함께 알린다. 성공한 페이지가
        하나도 없으면 완전 실패로 처리한다(`merged_pdf_path`는 `None`).
        """
        total = len(self.image_paths)
        try:
            self.work_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.exception("작업 디렉터리를 만들 수 없습니다: %s", self.work_dir)
            self.error_occurred.emit(str(exc))
            return

        for index, image_path in enumerate(self.image_paths, start=1):
            page_pdf_path = self.work_dir / f"page_{index:03d}.pdf"
            try:
                page_result = self._process_one(image_path, page_pdf_path)
            except Exception as exc:  # noqa: BLE001 - 페이지 단위 실패를 배치 전체 실패와 분리하려고 넓게 잡음
                logger.exception("페이지 처리 중 오류가 발생했습니다: %s", image_path)
                self.failed_pages.append((image_path, str(exc)))
            else:
                self.page_results.append(page_result)
                self.page_processed.emit(page_result)
            self.progress_changed.emit(index, total)

        if not self.page_results:
            self.error_occurred.emit(self._build_failure_summary(total))
            return

        try:
            merged_pdf_path = self.work_dir / "merged.pdf"
            assemble_pdf([r.page_pdf_path for r in self.page_results], merged_pdf_path)
        except Exception as exc:  # noqa: BLE001 - 외부 프로세스/파일 IO 경계라 광범위하게 잡아 신호로 전달
            logger.exception("PDF 병합 중 오류가 발생했습니다.")
            self.error_occurred.emit(str(exc))
            return

        self.merged_pdf_path = merged_pdf_path
        if self.failed_pages:
            # 일부 페이지는 실패했지만 나머지는 저장 가능하다는 것을 알린다
            # (merged_pdf_path가 이미 채워진 뒤에 emit해야 호출부가 "부분 성공"으로
            # 구분할 수 있다).
            self.error_occurred.emit(self._build_failure_summary(total))

    def _build_failure_summary(self, total: int) -> str:
        """실패한 페이지 목록을 사용자에게 보여줄 한 줄 요약 메시지로 만든다."""
        detail = "; ".join(f"{path.name}: {message}" for path, message in self.failed_pages)
        return f"{total}장 중 {len(self.failed_pages)}장 처리 실패: {detail}"

    def _process_one(self, image_path: Path, page_pdf_path: Path) -> PageResult:
        """이미지 한 장을 파일에서 읽어 `process_page_image()`로 처리한다."""
        image = load_image_bgr(image_path)
        if image is None:
            raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {image_path}")
        return process_page_image(
            image,
            image_path,
            page_pdf_path,
            lang_kwargs=self._lang_kwargs,
            preprocess_config=self._preprocess_config,
        )


class VectorizeWorker(QThread):
    """DIA-2: 이미 도형으로 처리된 페이지 한 장을 사용자가 명시적으로 요청했을 때 SVG로 변환한다.

    `PageResult.sharpened_image`(이미 선명화까지 끝난 결과)를 그대로 입력받으므로
    전처리/선명화를 다시 수행하지 않는다.
    """

    error_occurred = Signal(str)
    """vtracer 실행 중 예외가 발생했을 때 사용자에게 보여줄 메시지."""

    def __init__(self, sharpened_image: np.ndarray, output_svg: str | Path, parent=None) -> None:
        super().__init__(parent)
        self.sharpened_image = sharpened_image
        self.output_svg = Path(output_svg)
        self.svg_path: Path | None = None

    def run(self) -> None:
        try:
            self.svg_path = _vectorize_diagram(self.sharpened_image, self.output_svg)
        except Exception as exc:  # noqa: BLE001 - 외부 라이브러리(vtracer) 호출 경계
            logger.exception("도형 벡터화 중 오류가 발생했습니다.")
            self.error_occurred.emit(str(exc))


class ReprocessWorker(QThread):
    """Phase4-1(GUI-3 일부): 자르기/회전으로 보정한 이미지를 받아 파이프라인을 다시 실행한다.

    `image`는 이미 사용자가 지정한 회전/자르기가 적용된 배열이어야 한다(원본 raw
    사진에 `app.preprocess.manual_correction.apply_manual_correction`을 적용한
    결과) — 이 워커는 그 지점부터 `process_page_image()`(전처리→분류→라우팅)를
    다시 태우기만 한다. 업스케일(Real-ESRGAN)을 포함한 무거운 연산이므로
    `VectorizeWorker`와 같은 이유로 별도 QThread에서 실행한다.

    Phase4-4(RT-1 수동 오버라이드): `type_override`가 주어지면 자르기/회전과
    마찬가지로 사용자가 문서 유형을 직접 지정한 것이므로 재처리에도 그대로
    반영한다(`None`이면 기존과 동일하게 자동 분류).
    """

    error_occurred = Signal(str)
    """재처리 중 예외가 발생했을 때 사용자에게 보여줄 메시지."""

    def __init__(
        self,
        image: np.ndarray,
        input_path: Path,
        page_pdf_path: Path,
        *,
        lang: str | None = None,
        preprocess_config: PreprocessConfig | None = None,
        type_override: DocumentType | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.image = image
        self.input_path = Path(input_path)
        self.page_pdf_path = Path(page_pdf_path)
        self._lang_kwargs = {"lang": lang} if lang else {}
        self._preprocess_config = preprocess_config
        self._type_override = type_override
        self.page_result: PageResult | None = None

    def run(self) -> None:
        try:
            self.page_result = process_page_image(
                self.image,
                self.input_path,
                self.page_pdf_path,
                lang_kwargs=self._lang_kwargs,
                preprocess_config=self._preprocess_config,
                type_override=self._type_override,
            )
        except Exception as exc:  # noqa: BLE001 - 파이프라인 전체(전처리~라우팅) 재실행 경계
            logger.exception("페이지 재처리 중 오류가 발생했습니다: %s", self.input_path)
            self.error_occurred.emit(str(exc))
