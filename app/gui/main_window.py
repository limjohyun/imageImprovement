"""Phase1-5: 최소 GUI 메인 윈도우 (GUI-1 입력, GUI-2 미리보기, GUI-4 내보내기).

레이아웃은 단순하게 세 영역으로 나눈다:
  - 상단: 입력(폴더/파일 선택)·처리 시작·저장 버튼
  - 중단: 왼쪽 입력 파일 목록, 오른쪽 원본/처리 결과 나란히 보기
  - 하단: 진행 상태 텍스트

Phase1-6(TXT-3 텍스트 검수 UI)은 이 위젯 구조 위에 "선택된 페이지의 OCR 텍스트를
보여주고 수정하는" 패널만 추가하면 되도록, 처리 결과(`PageResult.text` 포함)를
`_results_by_input`에 이미 보관해둔다.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.worker import PageResult, ProcessingWorker

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
        self._work_dir: Path | None = None
        self._results_by_input: dict[str, PageResult] = {}
        self._merged_pdf_path: Path | None = None

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

        return layout

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
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(self, "처리 중", "이미 처리가 진행 중입니다.")
            return

        self._results_by_input.clear()
        self._merged_pdf_path = None
        self.save_button.setEnabled(False)
        self._set_input_controls_enabled(False)
        self.processed_preview_label.setText("아직 처리되지 않았습니다.")
        self.processed_preview_label.setPixmap(QPixmap())

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

    def _on_progress_changed(self, done: int, total: int) -> None:
        self.status_label.setText(f"{done}/{total} 처리 중...")

    def _on_page_processed(self, result: PageResult) -> None:
        self._results_by_input[str(result.input_path.resolve())] = result
        self._refresh_preview_if_selected(result.input_path)

    def _on_processing_error(self, message: str) -> None:
        QMessageBox.critical(self, "처리 오류", message)

    def _on_worker_finished(self) -> None:
        self._set_input_controls_enabled(True)
        worker = self._worker
        if worker is not None and worker.merged_pdf_path is not None:
            self._merged_pdf_path = worker.merged_pdf_path
            self.save_button.setEnabled(True)
            self.status_label.setText("처리 완료.")
        else:
            self.status_label.setText("처리에 실패했습니다.")
        self._worker = None
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

    def _refresh_preview_if_selected(self, input_path: Path) -> None:
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        selected_path = Path(items[0].data(_PATH_ROLE))
        if selected_path.resolve() == input_path.resolve():
            self._refresh_processed_preview(selected_path)

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
        worker = self._worker
        if worker is not None and worker.isRunning():
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
            worker.wait()
        if self._work_dir is not None:
            # PACS 스캔 등 민감한 문서 사본이 시스템 임시 디렉터리에 남지 않도록 종료 시 정리한다.
            shutil.rmtree(self._work_dir, ignore_errors=True)
        event.accept()
