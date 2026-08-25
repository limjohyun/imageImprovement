"""Phase1-5(GUI-1,2,4): 텍스트 처리 파이프라인 전체를 백그라운드 스레드에서 실행하는 워커.

전처리(`app.preprocess`) + OCR(`app.processors.text`) + PDF 병합(`app.pdf_assembly`)은
모두 무거운 연산(업스케일, Tesseract, OCRmyPDF/Ghostscript 서브프로세스 호출 등)이므로
GUI 메인 스레드에서 그대로 호출하면 UI가 블로킹된다. `QThread`를 상속해 이 전체 과정을
별도 스레드에서 실행한다.

QThread가 기본 제공하는 `finished` 시그널(인자 없음)을 그대로 사용한다 — 이 시그널을
커스텀 시그널로 덮어쓰면 pytest-qt 공식 예제(`qtbot.waitSignal(worker.finished, ...)`,
https://pytest-qt.readthedocs.io/en/latest/signals.html)가 기대하는 스레드 종료 알림
메커니즘과 이름이 충돌한다. 처리 실패는 별도 시그널(`error_occurred`)로 전달하고,
결과 값(성공 시 병합 PDF 경로 포함)은 스레드 종료 후에도 읽을 수 있도록 인스턴스
속성(`merged_pdf_path`, `page_results`)에 남겨둔다. `finished` 시그널을 받은 뒤
호출부가 `merged_pdf_path` 속성을 직접 읽으면 되므로 별도의 결과 전달용 시그널은
두지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.pdf_assembly.assemble import assemble_pdf
from app.processors.text import process_image_file

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """입력 이미지 한 장을 처리한 결과. Phase1-6(텍스트 검수 UI)이 `text`를 그대로 재사용한다."""

    input_path: Path
    page_pdf_path: Path
    text: str


class ProcessingWorker(QThread):
    """선택된 이미지 파일들을 순회하며 텍스트 파이프라인을 실행하고 최종 PDF로 병합한다."""

    progress_changed = Signal(int, int)
    """(완료한 페이지 수, 전체 페이지 수)."""

    page_processed = Signal(object)
    """페이지 한 장 처리가 끝날 때마다 `PageResult`를 실어 보낸다(미리보기 갱신용)."""

    error_occurred = Signal(str)
    """파이프라인 도중 예외가 발생했을 때 사용자에게 보여줄 메시지."""

    def __init__(
        self,
        image_paths: list[Path],
        work_dir: Path,
        *,
        lang: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.image_paths = [Path(p) for p in image_paths]
        self.work_dir = Path(work_dir)
        self._lang_kwargs = {"lang": lang} if lang else {}
        self.page_results: list[PageResult] = []
        self.merged_pdf_path: Path | None = None

    def run(self) -> None:
        """QThread 진입점. 예외는 밖으로 던지지 않고 `error_occurred`로 알린다."""
        total = len(self.image_paths)
        try:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            for index, image_path in enumerate(self.image_paths, start=1):
                page_pdf_path = self.work_dir / f"page_{index:03d}.pdf"
                result = process_image_file(image_path, page_pdf_path, **self._lang_kwargs)
                page_result = PageResult(
                    input_path=image_path, page_pdf_path=result.pdf_path, text=result.text
                )
                self.page_results.append(page_result)
                self.page_processed.emit(page_result)
                self.progress_changed.emit(index, total)

            merged_pdf_path = self.work_dir / "merged.pdf"
            assemble_pdf([r.page_pdf_path for r in self.page_results], merged_pdf_path)
        except Exception as exc:  # noqa: BLE001 - 외부 프로세스/파일 IO 경계라 광범위하게 잡아 신호로 전달
            logger.exception("텍스트 처리 파이프라인 실행 중 오류가 발생했습니다.")
            self.error_occurred.emit(str(exc))
            return

        self.merged_pdf_path = merged_pdf_path
