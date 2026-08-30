"""Phase1-5: 최소 GUI 메인 윈도우 (GUI-1 입력, GUI-2 미리보기, GUI-4 내보내기).

레이아웃은 단순하게 세 영역으로 나눈다:
  - 상단: 입력(폴더/파일 선택)·처리 시작·저장 버튼
  - 중단: 왼쪽 입력 파일 목록, 오른쪽 원본/처리 결과/인식된 텍스트 검수 패널
  - 하단: 진행 상태 텍스트

Phase1-6(TXT-3 텍스트 검수 UI): 선택된 페이지의 OCR 텍스트(`PageResult.text`)를
편집 가능한 `QPlainTextEdit`에 보여주고, 사용자가 수정하면 즉시(`textChanged`)
해당 `PageResult.text`에 반영한다. `PageResult`는 일반 `@dataclass`(mutable)라
필드를 직접 덮어써도 `_results_by_input`에 보관된 같은 객체를 가리키므로 별도의
"커밋" 단계 없이 실시간으로 데이터가 유지된다. PDF의 OCR 텍스트 레이어 재생성은
Phase1 범위 밖이다(수용 기준은 "확인/수정"이지 "PDF 재반영"이 아님).

Phase2-4(DIA-3 UI): `ProcessingWorker`가 자동 분류(`DocumentType`)까지 마친
`PageResult`를 돌려주므로, 도형으로 분류된 페이지를 선택하면 텍스트 검수 패널
대신 "도형으로 분류되어 텍스트 검수 대상이 아님"을 명확히 안내하고, 별도의
"SVG로 벡터화" 버튼(DIA-2)을 활성화한다. 벡터화는 사용자가 명시적으로 요청했을
때만 `VectorizeWorker`(별도 QThread)로 실행하고, 결과의 한계 고지 문구
(`VECTORIZATION_DISCLAIMER`)는 팝업(`QMessageBox.information`)과 상시 라벨
양쪽에 노출해 사용자가 놓치지 않게 한다.

Phase3-4(SCR-3 UI): 악보로 분류된 페이지도 도형과 마찬가지로 텍스트 검수 패널
대신 전용 안내를 보여준다. 대신 벡터화 버튼 자리에 "MuseScore에서 열기" 버튼을
두어, `PageResult.musicxml_path`가 채워져 있을 때만 활성화하고 클릭 시
`open_score_in_external_editor`로 MuseScore를 GUI 모드로 비블로킹 실행한다.
`open_score_in_external_editor`는 이미 `subprocess.Popen`으로 즉시 반환하므로
`VectorizeWorker` 같은 별도 QThread가 필요 없다 — 다만 반환된 `Popen`을 계속
참조로 들고 있지 않으면 프로세스가 실행 중일 때 GC되어 `ResourceWarning`이 날 수
있으므로, `self._open_musescore_processes` 리스트에 계속 보관한다.

Phase4-1(GUI-3 일부, 자르기/회전): 문서 유형과 무관하게 이미 처리된 모든 페이지에서
"자르기/회전" 버튼을 눌러 `CropRotateDialog`(숫자 입력 방식 — 마우스 드래그 대신
스핀박스/콤보박스, 구현 단순성과 pytest-qt 자동화 용이성 때문에 사용자와 합의된
방식)를 열 수 있다. 원본 raw 이미지(전처리 이전)를 다시 읽어 사용자가 지정한
회전/자르기(`app.preprocess.manual_correction.apply_manual_correction`)를 적용한
뒤, 그 결과로 전체 파이프라인(전처리~라우팅)을 `ReprocessWorker`(별도 QThread)로
다시 실행한다. 완료되면 해당 페이지의 `PageResult`를 갱신하고, `page_pdf_path`가
바뀌었으므로 최종 병합 PDF도 `app.pdf_assembly.assemble_pdf`로 다시 만든다
(`_rebuild_merged_pdf`). 재처리 도중 사용자가 다른 페이지로 이동해도 화면 갱신이
엉키지 않도록 Phase2-4의 `_is_currently_selected(path)` 가드 패턴을 그대로 쓰되,
`PageResult` 데이터 자체와 병합 PDF는 선택 여부와 무관하게 항상 갱신한다.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from pathlib import Path

import cv2
import pymupdf
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QCloseEvent, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.crop_rotate_dialog import CropRotateDialog
from app.gui.worker import PageResult, ProcessingWorker, ReprocessWorker, VectorizeWorker
from app.pdf_assembly.assemble import assemble_pdf
from app.preprocess.manual_correction import apply_manual_correction
from app.processors.diagram import VECTORIZATION_DISCLAIMER
from app.processors.score import ScoreRendererUnavailableError, open_score_in_external_editor
from app.router.classifier import DocumentType

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
_PATH_ROLE = Qt.ItemDataRole.UserRole
_DIGITS_RE = re.compile(r"(\d+)")


def _natural_sort_key(path: Path) -> list[str | int]:
    """`page2` < `page10`이 되도록 파일명 안 숫자를 정수로 비교하는 자연 정렬 키.

    사전식 정렬(`page1, page10, page11, page2` 순)로는 스캔한 문서의 실제
    페이지 순서가 조용히 뒤섞여 PDF-1(입력 순서대로 병합)이 깨지므로 필요하다.
    """
    return [int(part) if part.isdigit() else part.lower() for part in _DIGITS_RE.split(str(path))]


def render_pdf_first_page_to_pixmap(pdf_path: str | Path, *, dpi: int = 150) -> QPixmap:
    """PDF 첫 페이지를 미리보기용 `QPixmap`으로 렌더링한다 (GUI-2)."""
    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        pix = page.get_pixmap(dpi=dpi)
        image_format = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, image_format)
        # pix가 `with` 블록을 벗어나면 버퍼가 해제되므로 QPixmap으로 복사해 소유권을 넘긴다.
        return QPixmap.fromImage(image.copy())


class MainWindow(QMainWindow):
    """Phase1 최소 GUI: 이미지 일괄 입력 → 백그라운드 처리 → 원본/결과 비교 → PDF 저장."""

    processing_completed = Signal()
    """워커의 `finished`를 감싸 테스트/후속 로직이 완료 시점을 기다리기 쉽게 한다."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("이미지 → PDF 변환")
        self.resize(1000, 650)

        self._worker: ProcessingWorker | None = None
        self._vectorize_worker: VectorizeWorker | None = None
        self._reprocess_worker: ReprocessWorker | None = None
        self._open_musescore_processes: list = []
        """SCR-3: `open_score_in_external_editor`가 반환한 `subprocess.Popen`을 계속
        참조로 들고 있기 위한 리스트. 참조를 놓으면 프로세스가 아직 실행 중일 때
        CPython이 GC하면서 `ResourceWarning`을 낼 수 있다(code-reviewer 지적 사항)."""
        self._work_dir: Path | None = None
        self._results_by_input: dict[str, PageResult] = {}
        self._merged_pdf_path: Path | None = None
        self._reviewed_input_path: Path | None = None
        """텍스트 검수 위젯이 현재 어느 입력 파일의 결과를 보여주고 있는지 (수정 반영 대상)."""

        self._build_ui()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        root_layout.addLayout(self._build_toolbar())
        root_layout.addLayout(self._build_body(), stretch=1)

        self.status_label = QLabel("이미지를 추가하세요.")
        root_layout.addWidget(self.status_label)

    def _build_toolbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.select_folder_button = QPushButton("폴더 선택")
        self.select_folder_button.clicked.connect(self._on_select_folder_clicked)
        layout.addWidget(self.select_folder_button)

        self.select_files_button = QPushButton("파일 선택")
        self.select_files_button.clicked.connect(self._on_select_files_clicked)
        layout.addWidget(self.select_files_button)

        layout.addStretch(1)

        self.process_button = QPushButton("처리 시작")
        self.process_button.clicked.connect(self._start_processing)
        layout.addWidget(self.process_button)

        self.save_button = QPushButton("PDF로 저장")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        layout.addWidget(self.save_button)

        return layout

    def _build_body(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.file_list_widget = QListWidget()
        self.file_list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.file_list_widget, stretch=1)

        preview_layout = QHBoxLayout()
        preview_layout.addWidget(self._build_preview_group("원본", "original_preview_label"))
        preview_layout.addWidget(self._build_preview_group("처리 결과", "processed_preview_label"))
        layout.addLayout(preview_layout, stretch=2)

        right_column = QVBoxLayout()
        right_column.addWidget(self._build_crop_rotate_group())
        right_column.addWidget(self._build_text_review_group(), stretch=1)
        right_column.addWidget(self._build_diagram_group())
        right_column.addWidget(self._build_score_group())
        layout.addLayout(right_column, stretch=1)

        return layout

    def _build_crop_rotate_group(self) -> QGroupBox:
        """Phase4-1(GUI-3 일부): 문서 유형과 무관하게 모든 처리된 페이지에서 쓸 수 있는
        자르기/회전 기본 보정 버튼."""
        group = QGroupBox("자르기 / 회전 보정")
        group_layout = QVBoxLayout(group)

        button = QPushButton("자르기 / 회전...")
        button.setEnabled(False)
        button.clicked.connect(self._on_crop_rotate_clicked)
        group_layout.addWidget(button)
        self.crop_rotate_button = button

        return group

    def _build_text_review_group(self) -> QGroupBox:
        """TXT-3: 선택된 페이지의 OCR 인식 텍스트를 확인/수정하는 패널."""
        group = QGroupBox("인식된 텍스트")
        group_layout = QVBoxLayout(group)
        text_edit = QPlainTextEdit()
        text_edit.setPlaceholderText("페이지를 선택하세요.")
        text_edit.setEnabled(False)
        text_edit.textChanged.connect(self._on_review_text_changed)
        group_layout.addWidget(text_edit)
        self.text_review_edit = text_edit
        return group

    def _build_diagram_group(self) -> QGroupBox:
        """DIA-2/DIA-3: 도형으로 분류된 페이지의 벡터화 요청 버튼과 한계 고지 패널."""
        group = QGroupBox("도형 벡터화")
        group_layout = QVBoxLayout(group)

        button = QPushButton("SVG로 벡터화")
        button.setEnabled(False)
        button.clicked.connect(self._on_vectorize_clicked)
        group_layout.addWidget(button)
        self.vectorize_button = button

        disclaimer_label = QLabel("")
        disclaimer_label.setWordWrap(True)
        group_layout.addWidget(disclaimer_label)
        self.vectorization_disclaimer_label = disclaimer_label

        return group

    def _build_score_group(self) -> QGroupBox:
        """SCR-3: 악보로 분류된 페이지를 MuseScore GUI 편집기로 열어 오류를 직접 고치는 패널."""
        group = QGroupBox("악보 검수")
        group_layout = QVBoxLayout(group)

        button = QPushButton("MuseScore에서 열기")
        button.setEnabled(False)
        button.clicked.connect(self._on_open_in_musescore_clicked)
        group_layout.addWidget(button)
        self.open_in_musescore_button = button

        return group

    def _build_preview_group(self, title: str, label_attr: str) -> QGroupBox:
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        label = QLabel("미리볼 이미지가 없습니다.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(350, 450)
        group_layout.addWidget(label)
        setattr(self, label_attr, label)
        return group

    # ------------------------------------------------------------------
    # GUI-1: 입력
    # ------------------------------------------------------------------

    def _on_select_folder_clicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "이미지 폴더 선택")
        if not folder:
            return
        paths = [
            p
            for p in Path(folder).rglob("*")
            if p.is_file()
            and p.suffix.lower() in _IMAGE_EXTENSIONS
            and not p.name.startswith(".")  # macOS AppleDouble(._*) 등 리소스 포크 사이드카 제외
        ]
        if not paths:
            QMessageBox.warning(
                self, "이미지 없음", "선택한 폴더에서 이미지 파일을 찾지 못했습니다."
            )
            return
        self._add_image_paths(paths)

    def _on_select_files_clicked(self) -> None:
        filter_str = "이미지 파일 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)"
        files, _ = QFileDialog.getOpenFileNames(self, "이미지 파일 선택", "", filter_str)
        if not files:
            return
        self._add_image_paths([Path(f) for f in files])

    def _add_image_paths(self, paths: list[Path]) -> None:
        """파일 목록에 이미지 경로를 추가한다 (중복은 건너뛰고, 전체를 자연 정렬한다).

        폴더 스캔(사전식)과 파일 선택 다이얼로그(선택/OS 반환 순서)는 페이지 순서를
        보장하지 않으므로, 추가할 때마다 전체 목록을 파일명 기준 자연 정렬로 다시
        정렬해 PDF-1(입력 순서대로 병합)이 뒤섞이지 않게 한다.
        """
        existing = {
            self.file_list_widget.item(i).data(_PATH_ROLE)
            for i in range(self.file_list_widget.count())
        }
        all_paths = [
            Path(self.file_list_widget.item(i).data(_PATH_ROLE))
            for i in range(self.file_list_widget.count())
        ]
        added = 0
        for path in paths:
            resolved = path.resolve()
            if str(resolved) in existing:
                continue
            all_paths.append(resolved)
            existing.add(str(resolved))
            added += 1
        if not added:
            return

        all_paths.sort(key=_natural_sort_key)
        self.file_list_widget.clear()
        for resolved in all_paths:
            item = QListWidgetItem(resolved.name)
            item.setData(_PATH_ROLE, str(resolved))
            self.file_list_widget.addItem(item)

        total = self.file_list_widget.count()
        self.status_label.setText(f"이미지 {added}개를 추가했습니다. (총 {total}개)")

    def _image_paths_in_list(self) -> list[Path]:
        return [
            Path(self.file_list_widget.item(i).data(_PATH_ROLE))
            for i in range(self.file_list_widget.count())
        ]

    # ------------------------------------------------------------------
    # 처리 시작 (백그라운드 QThread)
    # ------------------------------------------------------------------

    def _start_processing(self) -> None:
        image_paths = self._image_paths_in_list()
        if not image_paths:
            QMessageBox.warning(self, "입력 없음", "처리할 이미지를 먼저 추가하세요.")
            return
        if self._running_background_workers():
            # HIGH #2(code-reviewer 지적): 재처리/벡터화 워커가 실행 중일 때 다시
            # "처리 시작"을 누르면 아래 shutil.rmtree가 그 워커가 곧 쓰려는
            # `self._work_dir`를 지워버리고 새 임시 디렉터리로 바꿔치기하게 되므로,
            # `self._worker`뿐 아니라 세 워커 전부를 확인해 막는다.
            QMessageBox.warning(
                self,
                "처리 중",
                "다른 작업(재처리/벡터화 등)이 진행 중입니다. 완료 후 다시 시도하세요.",
            )
            return
        if self._results_by_input:
            # 검수 패널에서 수정한 텍스트는 파일로 저장되지 않고 메모리(PageResult)에만
            # 있으므로, 재처리로 이전 결과를 지우기 전에 사용자에게 확인을 받는다.
            reply = QMessageBox.question(
                self,
                "다시 처리",
                "이전 처리 결과와 검수 중인 텍스트 수정 내용이 모두 사라집니다. 다시 처리할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._results_by_input.clear()
        self._merged_pdf_path = None
        self.save_button.setEnabled(False)
        self._set_input_controls_enabled(False)
        self.processed_preview_label.setText("아직 처리되지 않았습니다.")
        self.processed_preview_label.setPixmap(QPixmap())
        self._reset_text_review_panel()

        if self._work_dir is not None:
            # 재처리 시 이전 실행의 임시 작업 디렉터리가 계속 쌓이지 않도록 정리한다.
            shutil.rmtree(self._work_dir, ignore_errors=True)
        self._work_dir = Path(tempfile.mkdtemp(prefix="image_improvement_gui_"))
        worker = ProcessingWorker(image_paths, self._work_dir)
        worker.progress_changed.connect(self._on_progress_changed)
        worker.page_processed.connect(self._on_page_processed)
        worker.error_occurred.connect(self._on_processing_error)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self.status_label.setText(f"0/{len(image_paths)} 처리 중...")
        worker.start()

    def _set_input_controls_enabled(self, enabled: bool) -> None:
        self.select_folder_button.setEnabled(enabled)
        self.select_files_button.setEnabled(enabled)
        self.process_button.setEnabled(enabled)

    def _running_background_workers(
        self,
    ) -> list[ProcessingWorker | VectorizeWorker | ReprocessWorker]:
        """현재 실행 중인 백그라운드 워커(배치 처리/벡터화/재처리) 목록을 모아 반환한다.

        `_start_processing()`의 가드와 `closeEvent`가 "다른 작업이 실행 중인가"를
        똑같은 방식으로 확인해야 하므로(code-reviewer HIGH #2 지적) 여기 한 곳에
        모아두고 재사용한다.
        """
        return [
            worker
            for worker in (self._worker, self._vectorize_worker, self._reprocess_worker)
            if worker is not None and worker.isRunning()
        ]

    def _is_batch_processing(self) -> bool:
        """전체 배치 처리(`ProcessingWorker`)가 아직 실행 중인지."""
        return self._worker is not None and self._worker.isRunning()

    def _is_reprocessing(self) -> bool:
        """자르기/회전 재처리(`ReprocessWorker`)가 아직 실행 중인지."""
        return self._reprocess_worker is not None and self._reprocess_worker.isRunning()

    def _on_progress_changed(self, done: int, total: int) -> None:
        self.status_label.setText(f"{done}/{total} 처리 중...")

    def _on_page_processed(self, result: PageResult) -> None:
        self._results_by_input[str(result.input_path.resolve())] = result
        self._refresh_preview_if_selected(result.input_path)

    def _on_processing_error(self, message: str) -> None:
        """`ProcessingWorker.error_occurred`는 완전 실패와 부분 실패(일부 페이지만
        실패, 나머지는 병합돼 저장 가능) 모두에서 emit된다. `merged_pdf_path`가 이미
        채워져 있으면(워커 쪽에서 병합 후에 emit하도록 순서를 맞춰 뒀다) 부분 실패로
        보고 경고 수준으로, 아니면 완전 실패로 보고 치명적 오류로 안내한다.
        """
        worker = self._worker
        if worker is not None and worker.merged_pdf_path is not None:
            QMessageBox.warning(self, "일부 페이지 처리 실패", message)
        else:
            QMessageBox.critical(self, "처리 오류", message)

    def _on_worker_finished(self) -> None:
        self._set_input_controls_enabled(True)
        worker = self._worker
        if worker is not None and worker.merged_pdf_path is not None:
            self._merged_pdf_path = worker.merged_pdf_path
            self.save_button.setEnabled(True)
            if worker.failed_pages:
                self.status_label.setText(
                    f"처리 완료 (총 {len(worker.image_paths)}장 중 "
                    f"{len(worker.failed_pages)}장 실패, 나머지는 저장할 수 있습니다)."
                )
            else:
                self.status_label.setText("처리 완료.")
        else:
            self.status_label.setText("처리에 실패했습니다.")
        self._worker = None
        # HIGH #1(code-reviewer 지적): 배치 처리 중에는 `_refresh_crop_rotate_panel`이
        # 자르기/회전 버튼을 계속 비활성 상태로 둔다(`_is_batch_processing()`이 True).
        # 배치가 끝난 지금 시점에 다시 계산해줘야 현재 선택된 페이지의 버튼이
        # 정상적으로 활성화된다.
        items = self.file_list_widget.selectedItems()
        if items:
            self._refresh_crop_rotate_panel(Path(items[0].data(_PATH_ROLE)))
        self.processing_completed.emit()

    # ------------------------------------------------------------------
    # GUI-2: 미리보기
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        path = Path(items[0].data(_PATH_ROLE))
        self._show_original_preview(path)
        self._refresh_processed_preview(path)
        self._refresh_text_review(path)
        self._refresh_diagram_panel(path)
        self._refresh_score_panel(path)
        self._refresh_crop_rotate_panel(path)

    def _refresh_preview_if_selected(self, input_path: Path) -> None:
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        selected_path = Path(items[0].data(_PATH_ROLE))
        if selected_path.resolve() == input_path.resolve():
            self._refresh_processed_preview(selected_path)
            self._refresh_text_review(selected_path)
            self._refresh_diagram_panel(selected_path)
            self._refresh_score_panel(selected_path)
            self._refresh_crop_rotate_panel(selected_path)

    def _show_original_preview(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.original_preview_label.setText(f"이미지를 불러올 수 없습니다: {path.name}")
            return
        self._set_preview_pixmap(self.original_preview_label, pixmap)

    def _refresh_processed_preview(self, path: Path) -> None:
        result = self._results_by_input.get(str(path.resolve()))
        if result is None:
            self.processed_preview_label.setText("아직 처리되지 않았습니다.")
            self.processed_preview_label.setPixmap(QPixmap())
            return
        try:
            pixmap = render_pdf_first_page_to_pixmap(result.page_pdf_path)
        except Exception:  # noqa: BLE001 - 미리보기 렌더링 실패는 치명적이지 않으므로 텍스트로 대체
            logger.exception("처리 결과 미리보기 렌더링에 실패했습니다: %s", result.page_pdf_path)
            self.processed_preview_label.setText("미리보기를 렌더링할 수 없습니다.")
            return
        self._set_preview_pixmap(self.processed_preview_label, pixmap)

    def _set_preview_pixmap(self, label: QLabel, pixmap: QPixmap) -> None:
        target_size = label.size()
        label.setPixmap(
            pixmap.scaled(
                max(target_size.width(), 1),
                max(target_size.height(), 1),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ------------------------------------------------------------------
    # TXT-3: 텍스트 검수
    # ------------------------------------------------------------------

    def _refresh_text_review(self, path: Path) -> None:
        """선택된 페이지의 OCR 텍스트를 검수 위젯에 채운다.

        미처리 페이지와, 도형으로 분류되어 애초에 텍스트 검수 대상이 아닌 페이지는
        서로 다른 안내 문구로 구분해 보여준다 — 둘 다 "비활성화됨"으로만 보이면
        사용자가 도형 페이지를 버그(처리 누락)로 오인할 수 있다.
        """
        result = self._results_by_input.get(str(path.resolve()))
        self._reviewed_input_path = path
        # setPlainText가 textChanged를 다시 발생시켜 다른 페이지의 텍스트로
        # 되써지는 것을 막기 위해, 값을 채우는 동안은 시그널을 잠깐 막는다.
        # `QSignalBlocker`는 예외가 나도 스코프를 벗어나며 자동으로 해제되므로
        # blockSignals(True)/(False) 수동 쌍보다 안전하다.
        with QSignalBlocker(self.text_review_edit):
            if result is None:
                self.text_review_edit.clear()
                self.text_review_edit.setPlaceholderText("아직 처리되지 않았습니다.")
                self.text_review_edit.setEnabled(False)
            elif result.document_type == DocumentType.SCORE:
                self.text_review_edit.clear()
                self.text_review_edit.setPlaceholderText(
                    "이 페이지는 악보로 분류되어 텍스트 검수 대상이 아닙니다."
                )
                self.text_review_edit.setEnabled(False)
            elif result.document_type != DocumentType.TEXT:
                self.text_review_edit.clear()
                self.text_review_edit.setPlaceholderText(
                    "이 페이지는 도형으로 분류되어 텍스트 검수 대상이 아닙니다."
                )
                self.text_review_edit.setEnabled(False)
            else:
                self.text_review_edit.setPlainText(result.text or "")
                self.text_review_edit.setEnabled(True)

    def _refresh_diagram_panel(self, path: Path) -> None:
        """DIA-2/DIA-3: 도형 페이지일 때만 벡터화 버튼을 활성화하고 고지 문구를 갱신한다."""
        result = self._results_by_input.get(str(path.resolve()))
        is_diagram = result is not None and result.document_type == DocumentType.DIAGRAM
        self.vectorize_button.setEnabled(is_diagram)
        if result is not None and result.vectorization_disclaimer:
            self.vectorization_disclaimer_label.setText(result.vectorization_disclaimer)
        elif is_diagram:
            self.vectorization_disclaimer_label.setText("아직 벡터화하지 않았습니다.")
        else:
            self.vectorization_disclaimer_label.setText("")

    def _refresh_score_panel(self, path: Path) -> None:
        """SCR-3: 악보 페이지이고 MusicXML이 준비됐을 때만 "MuseScore에서 열기" 버튼을
        활성화한다."""
        result = self._results_by_input.get(str(path.resolve()))
        can_open = (
            result is not None
            and result.document_type == DocumentType.SCORE
            and result.musicxml_path is not None
        )
        self.open_in_musescore_button.setEnabled(can_open)

    def _refresh_crop_rotate_panel(self, path: Path) -> None:
        """Phase4-1(GUI-3 일부): 선택된 페이지가 이미 처리된 경우에만 자르기/회전
        버튼을 활성화한다. 문서 유형과 무관하게 모든 유형에서 동작하는 범용 기능이다.

        code-reviewer HIGH #1 지적: 결과가 있어도 전체 배치 처리(`ProcessingWorker`)가
        아직 실행 중이면 비활성화한다 — 그렇지 않으면 배치가 `merged.pdf`를 쓰는
        도중 재처리 완료 콜백(`_rebuild_merged_pdf`)도 같은 파일에 동시에 써서
        경합이 생길 수 있다. 재처리(`ReprocessWorker`)가 이미 실행 중일 때도
        마찬가지로 비활성화한다 — 지연된(TOCTOU) `finished` 콜백이 이 메서드를
        불러도 실제로 재처리가 끝나지 않았다면 버튼이 다시 켜지면 안 된다.
        """
        result = self._results_by_input.get(str(path.resolve()))
        can_reprocess = (
            result is not None and not self._is_batch_processing() and not self._is_reprocessing()
        )
        self.crop_rotate_button.setEnabled(can_reprocess)

    def _reset_text_review_panel(self) -> None:
        """새 배치 처리를 시작할 때 검수/벡터화/악보 검수/자르기·회전 패널을 초기화한다.

        현재 선택된 페이지가 있으면 `_refresh_text_review`/`_refresh_diagram_panel`/
        `_refresh_score_panel`/`_refresh_crop_rotate_panel`로 위임해 "아직 처리되지
        않았습니다" 상태를 보여주고(선택은 유지되므로 이쪽이 더 정확한 문구다),
        선택된 페이지가 없으면 안내 문구만 되돌린다.
        """
        items = self.file_list_widget.selectedItems()
        if items:
            path = Path(items[0].data(_PATH_ROLE))
            self._refresh_text_review(path)
            self._refresh_diagram_panel(path)
            self._refresh_score_panel(path)
            self._refresh_crop_rotate_panel(path)
            return
        self._reviewed_input_path = None
        with QSignalBlocker(self.text_review_edit):
            self.text_review_edit.clear()
            self.text_review_edit.setPlaceholderText("페이지를 선택하세요.")
            self.text_review_edit.setEnabled(False)
        self.vectorize_button.setEnabled(False)
        self.vectorization_disclaimer_label.setText("")
        self.open_in_musescore_button.setEnabled(False)
        self.crop_rotate_button.setEnabled(False)

    def _on_review_text_changed(self) -> None:
        """사용자가 텍스트를 수정하면 해당 페이지의 `PageResult.text`에 실시간으로 반영한다."""
        if self._reviewed_input_path is None:
            return
        result = self._results_by_input.get(str(self._reviewed_input_path.resolve()))
        if result is None:
            return
        result.text = self.text_review_edit.toPlainText()

    # ------------------------------------------------------------------
    # DIA-2/DIA-3: 도형 벡터화
    # ------------------------------------------------------------------

    def _on_vectorize_clicked(self) -> None:
        """선택된 도형 페이지를 SVG로 벡터화한다(사용자가 명시적으로 요청했을 때만 실행, DIA-2)."""
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        path = Path(items[0].data(_PATH_ROLE))
        result = self._results_by_input.get(str(path.resolve()))
        if (
            result is None
            or result.document_type != DocumentType.DIAGRAM
            or result.sharpened_image is None
            or self._work_dir is None
        ):
            return
        if self._vectorize_worker is not None and self._vectorize_worker.isRunning():
            QMessageBox.warning(self, "벡터화 진행 중", "이미 벡터화가 진행 중입니다.")
            return

        output_svg = self._work_dir / f"{result.page_pdf_path.stem}.svg"
        self.vectorize_button.setEnabled(False)
        self.status_label.setText("SVG로 벡터화하는 중...")

        worker = VectorizeWorker(result.sharpened_image, output_svg)
        worker.error_occurred.connect(lambda message, p=path: self._on_vectorize_error(message, p))
        worker.finished.connect(lambda: self._on_vectorize_finished(result, path))
        self._vectorize_worker = worker
        worker.start()

    def _is_currently_selected(self, path: Path) -> bool:
        """벡터화를 요청했던 페이지가 지금도 화면에 선택돼 있는지 확인한다.

        벡터화는 비동기(`VectorizeWorker`)로 진행되므로, 완료/실패 콜백이 돌아올
        때쯤엔 사용자가 이미 다른 페이지로 선택을 옮겼을 수 있다. 그 경우 화면에
        보이는 건 다른 페이지이므로 버튼/라벨 같은 화면 요소를 건드리면 안 된다.
        """
        items = self.file_list_widget.selectedItems()
        if not items:
            return False
        selected_path = Path(items[0].data(_PATH_ROLE))
        return selected_path.resolve() == path.resolve()

    def _on_vectorize_error(self, message: str, input_path: Path) -> None:
        """벡터화 실패를 알린다. 오류는 이미 로그로 남으므로(`VectorizeWorker`), 요청 당시
        페이지가 지금도 선택돼 있을 때만 팝업을 띄운다 — 그 사이 다른 페이지로 넘어갔다면
        엉뚱한 페이지를 보는 중에 "벡터화 오류"가 뜨는 것을 막고, 대신 상태표시줄에
        어떤 파일의 오류인지 조용히 남긴다(`_on_vectorize_finished`와 동일한 원칙)."""
        self._vectorize_worker = None
        if self._is_currently_selected(input_path):
            self.vectorize_button.setEnabled(True)
            QMessageBox.critical(self, "벡터화 오류", message)
        else:
            self.status_label.setText(f"벡터화 실패: {input_path.name}: {message}")

    def _on_vectorize_finished(self, result: PageResult, input_path: Path) -> None:
        """DIA-3: 벡터화가 끝나면 한계 고지 문구를 팝업과 상시 라벨 양쪽에 노출한다.

        단, 요청 당시 선택돼 있던 페이지(`input_path`)가 지금도 선택돼 있을 때만
        화면(버튼/라벨/팝업)을 갱신한다. 사용자가 그사이 다른 페이지로 넘어갔다면
        `result`(데이터)만 조용히 갱신해 두고, 화면은 나중에 그 페이지로 돌아왔을 때
        `_refresh_diagram_panel`이 알아서 최신 상태를 보여주도록 맡긴다.
        """
        worker = self._vectorize_worker
        self._vectorize_worker = None
        if worker is None or worker.svg_path is None:
            # 실패 시 `_on_vectorize_error`가 이미 메시지를 보여줬으므로 버튼 상태만 정리한다.
            if self._is_currently_selected(input_path):
                self.vectorize_button.setEnabled(True)
            return

        result.svg_path = worker.svg_path
        result.vectorization_disclaimer = VECTORIZATION_DISCLAIMER

        if not self._is_currently_selected(input_path):
            return

        self.vectorize_button.setEnabled(True)
        self.status_label.setText(f"벡터화했습니다: {worker.svg_path}")

        # DIA-3: 안 보이는 로그만으로는 부족하므로, 즉시 눈에 띄는 팝업으로 한 번 알리고
        # (사용자가 팝업을 닫은 뒤에도) 패널 라벨에 상시 노출해 다시 확인할 수 있게 한다.
        QMessageBox.information(self, "벡터화 완료 - 한계 고지", VECTORIZATION_DISCLAIMER)
        self._refresh_diagram_panel(input_path)

    # ------------------------------------------------------------------
    # SCR-3: 악보 오류 검수 (MuseScore 외부 편집기)
    # ------------------------------------------------------------------

    def _on_open_in_musescore_clicked(self) -> None:
        """선택된 악보 페이지를 MuseScore GUI 편집기로 연다(SCR-3).

        `open_score_in_external_editor`는 `subprocess.Popen`으로 즉시 반환하는
        비블로킹 호출이라 `VectorizeWorker` 같은 QThread가 필요 없다. 다만 반환된
        `Popen`을 계속 참조로 들고 있지 않으면 프로세스가 아직 실행 중일 때 GC되어
        `ResourceWarning`이 날 수 있으므로 `self._open_musescore_processes`에 보관한다.
        """
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        path = Path(items[0].data(_PATH_ROLE))
        result = self._results_by_input.get(str(path.resolve()))
        if (
            result is None
            or result.document_type != DocumentType.SCORE
            or result.musicxml_path is None
        ):
            return

        try:
            process = open_score_in_external_editor(result.musicxml_path)
        except ScoreRendererUnavailableError as exc:
            QMessageBox.critical(self, "MuseScore 없음", str(exc))
            return
        except FileNotFoundError as exc:
            QMessageBox.critical(self, "MusicXML 없음", str(exc))
            return
        except OSError as exc:
            # mscore 바이너리가 존재하지만 실행 권한이 없거나 손상된 경우 등,
            # Popen이 던질 수 있는 그 외의 OSError도 조용히 삼키지 않고 알린다.
            QMessageBox.critical(self, "MuseScore 실행 오류", str(exc))
            return

        # 이미 종료된 프로세스는 리스트에서 걷어내 세션 내내 계속 커지지 않게 한다.
        self._open_musescore_processes = [
            p for p in self._open_musescore_processes if p.poll() is None
        ]
        self._open_musescore_processes.append(process)
        self.status_label.setText(f"MuseScore에서 열었습니다: {result.musicxml_path.name}")

    # ------------------------------------------------------------------
    # Phase4-1(GUI-3 일부): 자르기 / 회전 보정
    # ------------------------------------------------------------------

    def _on_crop_rotate_clicked(self) -> None:
        """선택된 페이지의 원본 raw 이미지에 사용자가 지정한 자르기/회전을 적용한 뒤
        전체 파이프라인을 처음부터 다시 실행한다.

        이미 PRE-1~5 전처리(원근보정/deskew 등)를 거친 결과물을 자르면 안 되므로,
        `path`(원본 입력 파일)를 다시 읽어 그 raw 이미지에 보정을 적용한다.
        """
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        path = Path(items[0].data(_PATH_ROLE))
        result = self._results_by_input.get(str(path.resolve()))
        if result is None or self._work_dir is None:
            return
        if self._is_batch_processing():
            # HIGH #1(code-reviewer 지적): 버튼이 정상적으로 비활성화돼 있었다면
            # 이 클릭 자체가 발생하지 않지만, 방어적으로 한 번 더 막는다 — 배치가
            # merged.pdf를 쓰는 도중 재처리까지 시작되면 두 스레드가 같은 파일에
            # 동시에 쓸 수 있다.
            QMessageBox.warning(
                self, "처리 중", "전체 배치 처리가 진행 중입니다. 완료 후 다시 시도하세요."
            )
            return
        if self._is_reprocessing():
            QMessageBox.warning(self, "재처리 진행 중", "이미 재처리가 진행 중입니다.")
            return

        raw_image = cv2.imread(str(path))
        if raw_image is None:
            QMessageBox.critical(
                self, "이미지 읽기 실패", f"원본 이미지를 읽을 수 없습니다: {path}"
            )
            return
        original_height, original_width = raw_image.shape[:2]

        dialog = CropRotateDialog(
            original_width,
            original_height,
            initial_rotation_degrees=result.rotation_degrees,
            initial_crop_rect=result.crop_rect,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        rotation_degrees = dialog.rotation_degrees()
        crop_rect = dialog.crop_rect()
        try:
            corrected_image = apply_manual_correction(
                raw_image, rotation_degrees=rotation_degrees, crop_rect=crop_rect
            )
        except ValueError as exc:
            QMessageBox.critical(self, "보정 실패", str(exc))
            return

        self.crop_rotate_button.setEnabled(False)
        self.status_label.setText(f"보정을 반영해 다시 처리하는 중: {path.name}")

        worker = ReprocessWorker(corrected_image, path, result.page_pdf_path)
        # MEDIUM #3(code-reviewer 지적): `finished`/`error_occurred`가 GUI 스레드에서
        # 실제로 처리되기까지는 좁은 시간차가 있다. 그 사이 사용자가 같은 페이지를
        # 다시 열어 새 `ReprocessWorker`를 시작하면 `self._reprocess_worker`가 이미
        # 새 워커를 가리키게 되므로, 콜백 시점에 `self._reprocess_worker`를 다시
        # 읽지 않고 이 워커 인스턴스(`worker`)를 클로저로 그대로 넘겨 고정한다.
        worker.error_occurred.connect(
            lambda message, w=worker, p=path: self._on_reprocess_error(w, message, p)
        )
        worker.finished.connect(
            lambda w=worker: self._on_reprocess_finished(w, path, rotation_degrees, crop_rect)
        )
        self._reprocess_worker = worker
        worker.start()

    def _on_reprocess_error(self, worker: ReprocessWorker, message: str, input_path: Path) -> None:
        """재처리 실패를 알린다. 요청 당시 페이지가 지금도 선택돼 있을 때만 팝업을
        띄운다(`VectorizeWorker`/`_on_vectorize_error`와 동일한 원칙) — 그 사이 다른
        페이지로 넘어갔다면 상태표시줄에만 조용히 남긴다.

        MEDIUM #3: `self._reprocess_worker`는 이 콜백을 발생시킨 워커(`worker`)가
        지금도 "현재" 재처리 워커일 때만(즉 그 사이 새 재처리가 시작되지 않았을
        때만) 비운다 — 무조건 비우면 뒤늦게 도착한 예전 워커의 콜백이 이미 시작된
        새 워커의 참조를 지워버릴 수 있다.
        """
        if self._reprocess_worker is worker:
            self._reprocess_worker = None
        if self._is_currently_selected(input_path):
            self._refresh_crop_rotate_panel(input_path)
            QMessageBox.critical(self, "재처리 오류", message)
        else:
            self.status_label.setText(f"재처리 실패: {input_path.name}: {message}")

    def _on_reprocess_finished(
        self,
        worker: ReprocessWorker,
        input_path: Path,
        rotation_degrees: int,
        crop_rect: tuple[int, int, int, int],
    ) -> None:
        """재처리가 끝나면 `PageResult`를 갱신하고 최종 병합 PDF를 다시 만든다.

        `PageResult` 데이터와 병합 PDF 갱신은 선택 여부와 무관하게 항상 수행한다.
        화면(미리보기/검수 패널) 갱신만 요청 당시 페이지가 지금도 선택돼 있을 때로
        제한한다(Phase2-4의 `_is_currently_selected` 가드 패턴).

        MEDIUM #3(code-reviewer 지적): `self._reprocess_worker`를 다시 읽는 대신
        시그널을 발생시킨 워커 인스턴스(`worker`)를 인자로 직접 받는다. `self.
        _reprocess_worker`는 그 워커가 지금도 "현재" 워커일 때만 비운다 — 그렇지
        않으면(사용자가 그 사이 같은 페이지를 다시 열어 새 재처리를 시작한
        경우) 예전 워커의 뒤늦은 `finished`가 새 워커의 참조를 지우거나, 아직
        진행 중인 새 재처리를 "끝났다"고 오인해 버튼을 잘못 다시 활성화시킬 수
        있다(`_refresh_crop_rotate_panel`이 `_is_reprocessing()`도 함께 확인하므로
        버튼 자체는 이중으로 보호되지만, 참조 정리는 별도로 지켜야 한다).
        """
        if self._reprocess_worker is worker:
            self._reprocess_worker = None
        if worker.page_result is None:
            # 실패 시 `_on_reprocess_error`가 이미 메시지를 보여줬으므로 버튼 상태만 정리한다.
            if self._is_currently_selected(input_path):
                self._refresh_crop_rotate_panel(input_path)
            return

        new_result = worker.page_result
        new_result.crop_rect = crop_rect
        new_result.rotation_degrees = rotation_degrees
        self._results_by_input[str(input_path.resolve())] = new_result

        rebuild_error: str | None = None
        try:
            self._rebuild_merged_pdf()
        except Exception as exc:  # noqa: BLE001 - 파일 IO/외부 라이브러리(pymupdf) 경계
            logger.exception("보정 후 PDF 재병합에 실패했습니다.")
            rebuild_error = str(exc)

        if not self._is_currently_selected(input_path):
            self.status_label.setText(f"보정을 반영해 다시 처리했습니다: {input_path.name}")
            return

        self._refresh_crop_rotate_panel(input_path)
        self._refresh_processed_preview(input_path)
        self._refresh_text_review(input_path)
        self._refresh_diagram_panel(input_path)
        self._refresh_score_panel(input_path)
        self.status_label.setText(f"보정을 반영해 다시 처리했습니다: {input_path.name}")
        if rebuild_error is not None:
            QMessageBox.warning(self, "PDF 재병합 실패", rebuild_error)

    def _rebuild_merged_pdf(self) -> None:
        """자르기/회전 재처리로 한 페이지의 `page_pdf_path`가 바뀐 뒤, 파일 목록의
        원래 순서를 유지한 채 최종 병합 PDF를 다시 만든다 (PDF-1 재사용).

        아직 처리되지 않았거나 실패한 페이지는 최초 배치 처리(`ProcessingWorker`)와
        동일하게 건너뛴다 — 부분 성공 상태에서도 병합이 가능해야 한다.
        """
        if self._work_dir is None:
            return
        ordered_results = [
            self._results_by_input[str(p.resolve())]
            for p in self._image_paths_in_list()
            if str(p.resolve()) in self._results_by_input
        ]
        if not ordered_results:
            return
        merged_pdf_path = self._work_dir / "merged.pdf"
        assemble_pdf([r.page_pdf_path for r in ordered_results], merged_pdf_path)
        self._merged_pdf_path = merged_pdf_path
        self.save_button.setEnabled(True)

    # ------------------------------------------------------------------
    # GUI-4: 내보내기
    # ------------------------------------------------------------------

    def _on_save_clicked(self) -> None:
        if self._merged_pdf_path is None:
            QMessageBox.warning(self, "저장할 결과 없음", "먼저 처리를 완료하세요.")
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "PDF로 저장", "output.pdf", "PDF 파일 (*.pdf)"
        )
        if not save_path:
            return
        try:
            # OCRmyPDF가 만든 원본 바이트를 그대로 보존하기 위해 재직렬화 대신 단순 복사한다.
            shutil.copy2(self._merged_pdf_path, save_path)
        except Exception as exc:  # noqa: BLE001 - 파일 IO 경계, 사용자에게 원인을 알려야 함
            logger.exception("PDF 저장 중 오류가 발생했습니다: %s", save_path)
            QMessageBox.critical(self, "저장 실패", str(exc))
            return
        self.status_label.setText(f"저장했습니다: {save_path}")

    # ------------------------------------------------------------------
    # 종료 처리
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """백그라운드 워커가 실행 중일 때 창을 닫으면 스레드가 잘린 채 남는 것을 방지한다."""
        running_workers = self._running_background_workers()
        if running_workers:
            reply = QMessageBox.question(
                self,
                "처리 중",
                "아직 처리가 진행 중입니다. 처리가 끝날 때까지 기다렸다가 창을 닫을까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            # 개인용 데스크톱 도구 성격상 별도의 협조적 취소 메커니즘 없이,
            # 워커가 자연스럽게 끝나길 기다렸다가 닫는다.
            for w in running_workers:
                w.wait()
        if self._work_dir is not None:
            # PACS 스캔 등 민감한 문서 사본이 시스템 임시 디렉터리에 남지 않도록 종료 시 정리한다.
            shutil.rmtree(self._work_dir, ignore_errors=True)
        # SCR-3: 열려 있는 MuseScore 프로세스는 강제 종료하지 않는다 — 사용자가 편집
        # 중인 내용을 잃을 수 있다. 이 앱이 종료된 뒤에도 OS가 알아서 계속 살려두는
        # 것이 의도된 동작이므로, 참조 리스트만 정리한다(Popen 객체를 GC해도 이미 시작된
        # 자식 프로세스 자체는 종료되지 않는다).
        self._open_musescore_processes.clear()
        event.accept()
