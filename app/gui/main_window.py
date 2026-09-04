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

Phase4-2(GUI-3 전체, 검수 위젯 통합): 자르기/회전은 문서 유형과 무관한 공통 보정이므로
계속 오른쪽 컬럼 맨 위에 고정해 항상 보이게 두고, 그 아래 문서 유형별 전용 패널
(텍스트 검수/도형 벡터화/악보 검수)은 서로 동시에 볼 필요가 없으므로 `QStackedWidget`
(`review_stack`)으로 묶어 현재 선택된 페이지의 `document_type`에 맞는 패널 하나만
보이게 한다. 위젯 자체(`text_review_edit`/`vectorize_button`/
`vectorization_disclaimer_label`/`open_in_musescore_button`)와 그 활성화/비활성화
로직은 그대로 유지하고, `_refresh_type_review_panels()`가 기존 세 `_refresh_*`
호출을 한데 묶어 호출한 뒤 어떤 패널을 보여줄지만 추가로 결정한다(page 미선택·
미처리 상태의 기본 패널은 텍스트 검수 패널을 그대로 재사용 — 이미 "선택하세요"/
"처리되지 않았습니다" 안내를 자체적으로 보여주고 있어 별도의 빈 기본 패널을
새로 만들 필요가 없다).

Phase4-3(PDF-2, 페이지 재정렬/삭제): `file_list_widget`에
`QListWidget.DragDropMode.InternalMove`를 켜서 드래그 앤 드롭으로 순서를 바꿀 수
있게 하고, 내부 모델의 `rowsMoved` 시그널을 감지해 이미 처리된 페이지가 있으면
(`self._merged_pdf_path is not None`) `_rebuild_merged_pdf()`(Phase4-1에서 도입,
자르기/회전 재처리 후 병합 로직 그대로 재사용)를 다시 호출해 최종 PDF가 새 순서를
반영하게 한다. 삭제는 새 버튼("선택한 페이지 삭제") + `Delete`/`Backspace` 키
(macOS 키보드는 물리 키 이름이 Backspace뿐이라 둘 다 처리한다) 둘 다로 트리거되는
`_on_delete_pages_clicked()` 하나로 처리한다 — 목록에서 항목 제거, 결과 캐시
(`_results_by_input`)에서 키 제거, 남은 처리된 페이지가 있으면 재병합, 없으면
`_merged_pdf_path`를 `None`으로 되돌리고 저장 버튼을 비활성화한다. 다중 선택
삭제는 `QListWidget`이 원래 지원하는 범위를 그대로 반영할 뿐 별도 UI를 새로
만들지 않는다(선택 모드는 기존 기본값 `SingleSelection`을 그대로 둔다 — 기존
미리보기/검수 로직 다수가 "현재 선택된 페이지 1장"을 전제하므로 멀티 선택으로
바꾸면 그 쪽 의미가 모호해진다. 여러 장을 지우려면 한 장씩 지우면 된다).

재정렬/삭제 모두 배치 처리/벡터화/재처리 중 어느 하나라도 실행 중이면 막는다
(Phase4-1의 `_running_background_workers()` 재사용) — 진행 중인 작업이 참조하는
페이지 경로/인덱스가 목록 변경으로 어긋나는 것을 막기 위해서다. 삭제는 클릭/키
입력 시점에 그 자리에서 확인하면 되지만, 드래그 앤 드롭은 이미 순서가 바뀐 뒤에야
시그널이 오므로("취소"가 어색하다) 애초에 워커가 실행 중이면 `file_list_widget`의
드래그 자체를 비활성화(`NoDragDrop`)해 둔다 — 이 토글은 `_refresh_list_editing_
controls()`가 워커 시작/종료 지점마다(배치/벡터화/재처리 시작 및 완료·실패 콜백)
공통으로 호출해 갱신한다.

Phase4-4(RT-1 수동 오버라이드): 자르기/회전 그룹박스 바로 아래에 "문서 유형"
그룹박스(콤보박스 "자동"/"텍스트"/"도형"/"악보" + "적용" 버튼)를 추가한다. 자르기/
회전과 마찬가지로 문서 유형과 무관하게 이미 처리된 모든 페이지에서 쓸 수 있는
공통 보정이므로 같은 위치(review_stack 밖, `_build_body`의 공통 영역)에 둔다.
"적용"을 누르면 `_on_crop_rotate_clicked`와 동일한 패턴으로 원본 raw 이미지를 다시
읽어 그 페이지에 이미 저장된 `PageResult.crop_rect`/`rotation_degrees`를 그대로
`apply_manual_correction`으로 적용한 뒤(자르기/회전 보정이 사라지지 않게), 선택한
유형을 `type_override`로 넘겨 `ReprocessWorker`를 실행한다. 반대 방향도 대칭적으로
지켜진다 — `_on_crop_rotate_clicked`도 `PageResult.type_override`를 함께 넘겨,
자르기/회전만 다시 조정해도 이전에 지정해 둔 문서 유형이 조용히 자동으로 되돌아가지
않게 한다. 원래 `_refresh_crop_rotate_panel`이던 "결과 있음 + 배치 미실행 + 재처리
미실행" 조건 갱신 메서드를 `_refresh_manual_correction_controls`로 이름을 바꾸고
자르기/회전 버튼뿐 아니라 문서 유형 콤보박스/적용 버튼도 함께 갱신하도록 확장했다
(둘 다 "문서 유형과 무관한 공통 보정"이라는 같은 활성화 조건을 공유하기 때문).

PRE-1(GUI 수동 코너 오버라이드): 자동 원근보정(`app.preprocess.perspective.
correct_perspective`)은 "배경 없이 프레임을 꽉 채운 사진"에서 거의 항상 실패한다
(자동 검출 시 `DocumentCornersNotFoundError`, GUI는 기본적으로 `skip_perspective_
on_failure=True`라 조용히 건너뛴다). 자르기/회전(Phase4-1), 문서 유형(Phase4-4)과
같은 "공통 보정" 그룹에 "원근 보정 (수동)" 버튼을 두어, `PerspectiveCorrectionDialog`
(숫자 입력 방식)로 4모서리 좌표를 직접 지정한 뒤 `PreprocessConfig(corners=...,
skip_perspective_on_failure=False)`로 `ReprocessWorker`를 다시 실행한다. 초기값은
이전에 지정한 `PageResult.corners`가 있으면 그 값, 없으면 `detect_document_corners`를
한 번 시도해 성공하면 그 좌표, 실패하면(가장 흔한 실제 케이스) 이미지 네 귀퉁이를
채운다. `crop_rect`/`rotation_degrees`/`type_override`와 대칭적으로, 자르기/회전
또는 문서 유형만 다시 조정해도 이미 지정해 둔 `corners`가 조용히 사라지지 않도록
세 핸들러(`_on_crop_rotate_clicked`/`_on_type_override_apply_clicked`/
`_on_perspective_correction_clicked`) 모두 `result.corners`를 서로 이어받는다.
단, 이 이어받기는 이미지 크기가 바뀌지 않았을 때만 유효하다 — 자르기/회전으로
이미지 크기가 달라지면 이전 좌표는 더 이상 맞지 않으므로(범위 밖 좌표로 원근
변환하면 예외 없이 대부분 검은색인 손상된 이미지가 조용히 만들어진다),
`_preprocess_config_for_corners()`가 재처리 시점 이미지 크기와 비교해 범위를
벗어나면 폐기하고 자동 검출로 되돌리며 상태표시줄로 알린다(HIGH, code-reviewer
지적).

Phase5-1(BKP-1, 로컬 저장 우선 보장 + 백업 설정 UI): 툴바에 "백업 사용"
체크박스를 추가해 `app.backup.BackupSettings`(QSettings 기반, 기본값 False)에
상태를 즉시 저장/복원한다. `_on_save_clicked()`가 로컬 PDF 저장(GUI-4)을 실제로
마친 뒤에만 `_attempt_backup()` 훅을 호출하도록 순서를 고정한다 — 백업이
꺼져 있으면 훅 자체가 아무 것도 하지 않고(오프라인 보장, BKP-3의 전조), 켜져
있어도 실제 업로드(`app.backup.uploader.upload_pdf`)는 아직 Phase5-2가 채울
no-op 스텁이다. `_attempt_backup()`은 훅 호출을 try/except로 감싸 예외가
전파되지 않게 해, 백업 실패가 이미 끝난 로컬 저장 결과나 GUI 반응성에 영향을
주지 않게 한다(BKP-1 핵심 계약).
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pymupdf
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QCloseEvent, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.backup.settings import BackupSettings
from app.backup.uploader import upload_pdf
from app.gui.crop_rotate_dialog import CropRotateDialog, PerspectiveCorrectionDialog
from app.gui.worker import PageResult, ProcessingWorker, ReprocessWorker, VectorizeWorker
from app.ingest import load_image_bgr
from app.pdf_assembly.assemble import assemble_pdf
from app.preprocess.manual_correction import apply_manual_correction
from app.preprocess.perspective import detect_document_corners
from app.preprocess.pipeline import PreprocessConfig
from app.processors.diagram import VECTORIZATION_DISCLAIMER
from app.processors.score import ScoreRendererUnavailableError, open_score_in_external_editor
from app.router.classifier import DocumentType

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
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
        self._backup_settings = BackupSettings()
        """Phase5-1(BKP-1): 백업 활성화 여부(기본값 False)를 저장/조회하는 얇은 래퍼."""

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

        backup_checkbox = QCheckBox("백업 사용")
        backup_checkbox.setToolTip(
            "켜면 PDF를 로컬에 저장한 뒤 클라우드 백업을 시도합니다"
            "(현재는 자리만 마련된 상태이며 실제 업로드는 아직 구현되지 않았습니다)."
        )
        # 저장된 값으로 먼저 초기화한 뒤 시그널을 연결해, 초기화 과정에서
        # `_on_backup_enabled_toggled`가 불필요하게 호출되지 않게 한다.
        backup_checkbox.setChecked(self._backup_settings.is_backup_enabled())
        backup_checkbox.toggled.connect(self._on_backup_enabled_toggled)
        layout.addWidget(backup_checkbox)
        self.backup_enabled_checkbox = backup_checkbox

        return layout

    def _build_body(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        layout.addLayout(self._build_file_list_column(), stretch=1)

        preview_layout = QHBoxLayout()
        preview_layout.addWidget(self._build_preview_group("원본", "original_preview_label"))
        preview_layout.addWidget(self._build_preview_group("처리 결과", "processed_preview_label"))
        layout.addLayout(preview_layout, stretch=2)

        right_column = QVBoxLayout()
        right_column.addWidget(self._build_crop_rotate_group())
        right_column.addWidget(self._build_type_override_group())
        right_column.addWidget(self._build_review_stack(), stretch=1)
        layout.addLayout(right_column, stretch=1)

        return layout

    def _build_file_list_column(self) -> QVBoxLayout:
        """Phase4-3(PDF-2): 입력 파일 목록 + 재정렬(드래그)/삭제 UI."""
        layout = QVBoxLayout()

        list_widget = QListWidget()
        list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self.file_list_widget = list_widget
        layout.addWidget(list_widget, stretch=1)

        # macOS 키보드에는 물리적인 Delete(Forward Delete) 키가 없는 기종이 많아
        # Backspace(실제로는 Qt.Key_Backspace)도 함께 삭제 단축키로 처리한다.
        for key_sequence in (QKeySequence(Qt.Key.Key_Delete), QKeySequence(Qt.Key.Key_Backspace)):
            shortcut = QShortcut(key_sequence, list_widget)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._on_delete_pages_clicked)

        delete_button = QPushButton("선택한 페이지 삭제")
        delete_button.setEnabled(False)
        delete_button.clicked.connect(self._on_delete_pages_clicked)
        layout.addWidget(delete_button)
        self.delete_page_button = delete_button

        return layout

    def _build_review_stack(self) -> QStackedWidget:
        """Phase4-2(GUI-3 전체): 문서 유형별 전용 검수 패널(텍스트/도형/악보)을
        `QStackedWidget`으로 묶어, 현재 선택된 페이지의 `document_type`에 맞는
        패널 하나만 보이게 한다. 자르기/회전은 유형과 무관한 공통 보정이라 이
        스택 밖(호출부인 `_build_body`)에 항상 고정해 둔다.

        텍스트 검수 패널(`QPlainTextEdit`)은 원래도 세로로 확장되는 게 자연스러워
        그대로 스택에 넣지만, 도형/악보 패널은 버튼 몇 개뿐인 컴팩트한 그룹박스라
        `QStackedWidget`이 강제로 늘리면 그룹박스 테두리 안에 눈에 띄는 빈 공간이
        생긴다(code-reviewer MEDIUM #1). 이를 막기 위해 그룹박스를 작은 래퍼
        위젯으로 감싸 `addStretch`로 남는 공간을 그룹박스 밖(중립적인 배경)으로
        빼낸 뒤 그 래퍼를 스택 페이지로 등록한다.
        """
        stack = QStackedWidget()
        self._text_review_page = self._build_text_review_group()
        self._diagram_review_page = self._wrap_with_top_stretch(self._build_diagram_group())
        self._score_review_page = self._wrap_with_top_stretch(self._build_score_group())
        stack.addWidget(self._text_review_page)
        stack.addWidget(self._diagram_review_page)
        stack.addWidget(self._score_review_page)
        self.review_stack = stack
        return stack

    @staticmethod
    def _wrap_with_top_stretch(content: QWidget) -> QWidget:
        """컴팩트한 위젯을 위쪽에 고정하고 남는 세로 공간은 아래로 밀어내는 래퍼."""
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(content)
        wrapper_layout.addStretch(1)
        return wrapper

    def _build_crop_rotate_group(self) -> QGroupBox:
        """Phase4-1(GUI-3 일부)+PRE-1(GUI 수동 코너 오버라이드): 문서 유형과 무관하게
        모든 처리된 페이지에서 쓸 수 있는 자르기/회전/원근보정 기본 보정 버튼들."""
        group = QGroupBox("공통 보정")
        group_layout = QVBoxLayout(group)

        button = QPushButton("자르기 / 회전...")
        button.setEnabled(False)
        button.clicked.connect(self._on_crop_rotate_clicked)
        group_layout.addWidget(button)
        self.crop_rotate_button = button

        perspective_button = QPushButton("원근 보정 (수동)...")
        perspective_button.setEnabled(False)
        perspective_button.clicked.connect(self._on_perspective_correction_clicked)
        group_layout.addWidget(perspective_button)
        self.perspective_correction_button = perspective_button

        return group

    def _build_type_override_group(self) -> QGroupBox:
        """Phase4-4(RT-1 수동 오버라이드): 문서 유형과 무관하게 모든 처리된 페이지에서
        자동 분류 결과를 사람이 직접 바로잡을 수 있는 콤보박스 + 적용 버튼."""
        group = QGroupBox("문서 유형")
        group_layout = QHBoxLayout(group)

        combo = QComboBox()
        combo.addItem("자동", None)
        combo.addItem("텍스트", DocumentType.TEXT)
        combo.addItem("도형", DocumentType.DIAGRAM)
        combo.addItem("악보", DocumentType.SCORE)
        combo.setEnabled(False)
        group_layout.addWidget(combo, stretch=1)
        self.type_override_combo = combo

        apply_button = QPushButton("적용")
        apply_button.setEnabled(False)
        apply_button.clicked.connect(self._on_type_override_apply_clicked)
        group_layout.addWidget(apply_button)
        self.type_override_apply_button = apply_button

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
        filter_str = "이미지 파일 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.heic *.heif)"
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

    # ------------------------------------------------------------------
    # Phase5-1(BKP-1): 백업 설정
    # ------------------------------------------------------------------

    def _on_backup_enabled_toggled(self, checked: bool) -> None:
        """"백업 사용" 체크박스 상태를 즉시 `BackupSettings`에 영속화한다."""
        self._backup_settings.set_backup_enabled(checked)

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
        # code-reviewer HIGH 지적: QThread.isRunning()은 start() 호출 전까지 항상
        # False이므로, _refresh_list_editing_controls()는 반드시 worker.start()
        # 이후에 호출해야 "워커 실행 중"을 정확히 감지해 드래그/삭제를 막는다.
        worker.start()
        self._refresh_list_editing_controls()
        self.status_label.setText(f"0/{len(image_paths)} 처리 중...")

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

    def _refresh_list_editing_controls(self) -> None:
        """Phase4-3(PDF-2): 재정렬(드래그)/삭제 가능 여부를 워커 실행 상태에 맞춰 갱신한다.

        배치 처리/벡터화/재처리 중 어느 하나라도 실행 중이면 목록을 바꾸지 못하게
        막는다(`_running_background_workers()` 재사용, Phase4-1과 동일한 원칙) —
        진행 중인 워커가 참조하는 페이지 경로/인덱스가 목록 변경으로 어긋나는 것을
        막기 위해서다. 드래그는 이미 이동한 뒤에야 시그널이 오므로("취소"가 어색
        하다) 애초에 `NoDragDrop`으로 비활성화해 시도 자체를 막는다. 삭제 버튼은
        선택된 항목이 없을 때도 당연히 비활성화한다.
        """
        editing_allowed = not self._running_background_workers()
        self.file_list_widget.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
            if editing_allowed
            else QAbstractItemView.DragDropMode.NoDragDrop
        )
        has_selection = bool(self.file_list_widget.selectedItems())
        self.delete_page_button.setEnabled(editing_allowed and has_selection)

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
        # HIGH #1(code-reviewer 지적): 배치 처리 중에는 `_refresh_manual_correction_controls`이
        # 자르기/회전 버튼을 계속 비활성 상태로 둔다(`_is_batch_processing()`이 True).
        # 배치가 끝난 지금 시점에 다시 계산해줘야 현재 선택된 페이지의 버튼이
        # 정상적으로 활성화된다. 재정렬/삭제 가능 여부(Phase4-3)도 같은 이유로 갱신한다.
        items = self.file_list_widget.selectedItems()
        if items:
            self._refresh_manual_correction_controls(Path(items[0].data(_PATH_ROLE)))
        self._refresh_list_editing_controls()
        self.processing_completed.emit()

    # ------------------------------------------------------------------
    # GUI-2: 미리보기
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        self._refresh_list_editing_controls()
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        path = Path(items[0].data(_PATH_ROLE))
        self._show_original_preview(path)
        self._refresh_processed_preview(path)
        self._refresh_type_review_panels(path)
        self._refresh_manual_correction_controls(path)

    def _refresh_preview_if_selected(self, input_path: Path) -> None:
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        selected_path = Path(items[0].data(_PATH_ROLE))
        if selected_path.resolve() == input_path.resolve():
            self._refresh_processed_preview(selected_path)
            self._refresh_type_review_panels(selected_path)
            self._refresh_manual_correction_controls(selected_path)

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

    def _refresh_type_review_panels(self, path: Path) -> None:
        """선택된 페이지의 문서 유형별 검수 패널(텍스트/도형/악보) 내용을 갱신하고,
        그중 `document_type`에 맞는 패널 하나만 `review_stack`에 보여준다 (Phase4-2,
        GUI-3 전체). 세 패널을 항상 함께 갱신해야 하는 호출부(선택 변경, 처리 완료,
        재처리 완료 등)가 공통으로 쓰는 진입점이다.
        """
        self._refresh_text_review(path)
        self._refresh_diagram_panel(path)
        self._refresh_score_panel(path)
        result = self._results_by_input.get(str(path.resolve()))
        self._show_review_page_for(result.document_type if result is not None else None)

    def _show_review_page_for(self, document_type: DocumentType | None) -> None:
        """`review_stack`에서 문서 유형에 맞는 패널로 전환한다.

        미처리 페이지(`document_type=None`)와 TEXT 페이지는 텍스트 검수 패널을
        그대로 공유한다 — 그 패널이 이미 "선택하세요"/"아직 처리되지 않았습니다"
        안내를 자체적으로 보여주므로 별도의 빈 기본 패널을 새로 만들 필요가 없다.
        """
        if document_type == DocumentType.DIAGRAM:
            self.review_stack.setCurrentWidget(self._diagram_review_page)
        elif document_type == DocumentType.SCORE:
            self.review_stack.setCurrentWidget(self._score_review_page)
        else:
            self.review_stack.setCurrentWidget(self._text_review_page)

    def _refresh_manual_correction_controls(self, path: Path) -> None:
        """Phase4-1(GUI-3 일부)+Phase4-4(RT-1 수동 오버라이드)+PRE-1(GUI 수동 코너
        오버라이드): 선택된 페이지가 이미 처리된 경우에만 자르기/회전 버튼, 원근
        보정(수동) 버튼, 문서 유형 콤보박스/적용 버튼을 활성화한다. 문서 유형과
        무관하게 모든 유형에서 동작하는 범용 기능이다.

        code-reviewer HIGH #1 지적: 결과가 있어도 전체 배치 처리(`ProcessingWorker`)가
        아직 실행 중이면 비활성화한다 — 그렇지 않으면 배치가 `merged.pdf`를 쓰는
        도중 재처리 완료 콜백(`_rebuild_merged_pdf`)도 같은 파일에 동시에 써서
        경합이 생길 수 있다. 재처리(`ReprocessWorker`)가 이미 실행 중일 때도
        마찬가지로 비활성화한다 — 지연된(TOCTOU) `finished` 콜백이 이 메서드를
        불러도 실제로 재처리가 끝나지 않았다면 버튼이 다시 켜지면 안 된다.

        문서 유형 콤보박스는 그 페이지에 저장된 `PageResult.type_override`(있으면
        직전에 사용자가 지정한 값, 없으면 "자동")로 현재 선택을 맞춰 보여준다 —
        `setCurrentIndex`가 다시 `_on_type_override_apply_clicked`를 부르지 않도록
        시그널을 잠깐 막는다(값을 보여주기만 할 뿐 적용을 트리거하면 안 된다).
        """
        result = self._results_by_input.get(str(path.resolve()))
        can_reprocess = (
            result is not None and not self._is_batch_processing() and not self._is_reprocessing()
        )
        self.crop_rotate_button.setEnabled(can_reprocess)
        self.perspective_correction_button.setEnabled(can_reprocess)

        self.type_override_apply_button.setEnabled(can_reprocess)
        with QSignalBlocker(self.type_override_combo):
            self.type_override_combo.setEnabled(can_reprocess)
            override = result.type_override if result is not None else None
            index = self.type_override_combo.findData(override)
            self.type_override_combo.setCurrentIndex(max(index, 0))

    def _reset_text_review_panel(self) -> None:
        """새 배치 처리를 시작하거나(Phase1) 페이지를 삭제했을 때(Phase4-3) 검수/
        벡터화/악보 검수/자르기·회전 패널을 초기화한다.

        현재 선택된 페이지가 있으면 `_refresh_text_review`/`_refresh_diagram_panel`/
        `_refresh_score_panel`/`_refresh_manual_correction_controls`로 위임해 "아직 처리되지
        않았습니다" 상태를 보여주고(선택은 유지되므로 이쪽이 더 정확한 문구다),
        선택된 페이지가 없으면(페이지 삭제 직후에는 항상 이 경우다) 안내 문구만
        되돌린다.
        """
        items = self.file_list_widget.selectedItems()
        if items:
            path = Path(items[0].data(_PATH_ROLE))
            self._refresh_type_review_panels(path)
            self._refresh_manual_correction_controls(path)
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
        self.perspective_correction_button.setEnabled(False)
        self.type_override_apply_button.setEnabled(False)
        with QSignalBlocker(self.type_override_combo):
            self.type_override_combo.setEnabled(False)
            self.type_override_combo.setCurrentIndex(0)
        self._show_review_page_for(None)

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
        # code-reviewer HIGH 지적: start() 호출 전에는 isRunning()이 항상 False이므로
        # 반드시 start() 이후에 갱신해야 한다.
        worker.start()
        self._refresh_list_editing_controls()

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
        self._refresh_list_editing_controls()
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
        self._refresh_list_editing_controls()
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

        raw_image = load_image_bgr(path)
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

        # Phase4-4: 자르기/회전만 다시 조정하는 요청이므로, 이 페이지에 이미 지정된
        # 문서 유형 오버라이드(있다면)는 그대로 이어간다 — 유형은 그대로 두고 자르기/
        # 회전만 바꿨는데 유형이 조용히 자동으로 되돌아가면 안 된다.
        type_override = result.type_override
        # PRE-1: 자르기/회전만 다시 조정하는 요청이므로, 이미 지정된 수동 원근보정
        # 코너(있다면)도 함께 이어간다 — 그렇지 않으면 사용자가 힘들게 지정한 코너가
        # 자르기/회전만 바꿔도 조용히 사라진다(type_override와 동일한 종류의 회귀).
        corners = result.corners
        preprocess_config = self._preprocess_config_for_corners(
            corners, corrected_image.shape[:2]
        )
        if corners is not None and preprocess_config is None:
            # HIGH(code-reviewer 지적): 새 자르기/회전으로 이미지 크기가 바뀌어 이전
            # 코너 좌표가 더 이상 유효하지 않다 — 폐기하고 자동 검출로 되돌아간다는
            # 것을 사용자에게 알린다.
            corners = None
            status_message = (
                "이전 원근보정 좌표가 새 자르기 크기와 맞지 않아 자동 검출로 "
                f"되돌렸습니다: {path.name}"
            )
        else:
            status_message = f"보정을 반영해 다시 처리하는 중: {path.name}"
        self._disable_manual_correction_controls()
        self.status_label.setText(status_message)

        worker = ReprocessWorker(
            corrected_image,
            path,
            result.page_pdf_path,
            preprocess_config=preprocess_config,
            type_override=type_override,
        )
        # MEDIUM #3(code-reviewer 지적): `finished`/`error_occurred`가 GUI 스레드에서
        # 실제로 처리되기까지는 좁은 시간차가 있다. 그 사이 사용자가 같은 페이지를
        # 다시 열어 새 `ReprocessWorker`를 시작하면 `self._reprocess_worker`가 이미
        # 새 워커를 가리키게 되므로, 콜백 시점에 `self._reprocess_worker`를 다시
        # 읽지 않고 이 워커 인스턴스(`worker`)를 클로저로 그대로 넘겨 고정한다.
        worker.error_occurred.connect(
            lambda message, w=worker, p=path: self._on_reprocess_error(w, message, p)
        )
        worker.finished.connect(
            lambda w=worker: self._on_reprocess_finished(
                w, path, rotation_degrees, crop_rect, type_override, corners=corners
            )
        )
        self._reprocess_worker = worker
        # code-reviewer HIGH 지적: start() 호출 전에는 isRunning()이 항상 False이므로
        # 반드시 start() 이후에 갱신해야 한다.
        worker.start()
        self._refresh_list_editing_controls()

    def _preprocess_config_for_corners(
        self, corners: np.ndarray | None, image_shape: tuple[int, int]
    ) -> PreprocessConfig | None:
        """PRE-1: 이 페이지에 이미 지정된 수동 원근보정 코너(있다면)를 재처리에도
        그대로 반영한다.

        `corners`가 있으면 `skip_perspective_on_failure=False`로 강제해 그 좌표를
        무조건 사용하게 한다(사용자가 명시적으로 지정한 값이므로 자동 검출로 되돌아가면
        안 된다). 없으면 `None`을 그대로 반환해 기존과 동일하게 기본 `PreprocessConfig`
        (자동 검출, 실패 시 건너뛰기)에 맡긴다.

        `image_shape`(`(height, width)`, 이번 재처리에 실제로 넘길 `corrected_image`
        기준)와 비교해 `corners`가 이 범위(`[0, width] x [0, height]`)를 벗어나면
        폐기하고 `None`을 반환한다(HIGH, code-reviewer 지적) — `corners`는 그것이
        지정됐던 당시 이미지 크기 기준 좌표라서, 이후 자르기/회전으로 이미지 크기가
        바뀌면 더 이상 유효하지 않다. `warp_to_corners`/`cv2.warpPerspective`는 범위
        밖 좌표를 예외 없이 조용히 받아들여 대부분 검은색인 손상된 이미지를 만들어
        내므로, 여기서 미리 걸러 자동 검출로 안전하게 폴백시켜야 한다. 상태 메시지
        표시는 호출부(세 재처리 진입점)가 이 반환값이 `None`인지(원래 `corners`가
        `None`이 아니었는데도)로 판단해 담당한다.
        """
        if corners is None:
            return None
        height, width = image_shape
        out_of_bounds = (
            np.any(corners[:, 0] < 0)
            or np.any(corners[:, 0] > width)
            or np.any(corners[:, 1] < 0)
            or np.any(corners[:, 1] > height)
        )
        if out_of_bounds:
            return None
        return PreprocessConfig(corners=corners, skip_perspective_on_failure=False)

    def _disable_manual_correction_controls(self) -> None:
        """재처리를 시작하는 순간 자르기/회전 버튼과 문서 유형 컨트롤을 모두 잠근다.

        재처리 진행 중에는 어느 쪽으로 다시 클릭해도 같은 페이지에 대한 두 번째
        `ReprocessWorker`가 겹쳐 시작되면 안 되므로, 세 진입점(`_on_crop_rotate_
        clicked`/`_on_type_override_apply_clicked`/`_on_perspective_correction_clicked`)이
        공통으로 호출한다.
        """
        self.crop_rotate_button.setEnabled(False)
        self.perspective_correction_button.setEnabled(False)
        self.type_override_apply_button.setEnabled(False)
        self.type_override_combo.setEnabled(False)

    def _on_type_override_apply_clicked(self) -> None:
        """RT-1 수동 오버라이드: 선택된 페이지의 문서 유형을 사용자가 고른 값으로
        강제 지정해 다시 처리한다.

        `_on_crop_rotate_clicked`와 같은 패턴을 쓰되, 자르기/회전 다이얼로그를 새로
        열지 않고 그 페이지에 이미 저장돼 있던 `crop_rect`/`rotation_degrees`를
        그대로 다시 적용한다 — 유형만 바꾸는 요청인데 기존 자르기/회전 보정이
        사라지면 안 되기 때문이다.
        """
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        path = Path(items[0].data(_PATH_ROLE))
        result = self._results_by_input.get(str(path.resolve()))
        if result is None or self._work_dir is None:
            return
        if self._is_batch_processing():
            QMessageBox.warning(
                self, "처리 중", "전체 배치 처리가 진행 중입니다. 완료 후 다시 시도하세요."
            )
            return
        if self._is_reprocessing():
            QMessageBox.warning(self, "재처리 진행 중", "이미 재처리가 진행 중입니다.")
            return

        raw_image = load_image_bgr(path)
        if raw_image is None:
            QMessageBox.critical(
                self, "이미지 읽기 실패", f"원본 이미지를 읽을 수 없습니다: {path}"
            )
            return

        rotation_degrees = result.rotation_degrees
        crop_rect = result.crop_rect
        try:
            corrected_image = apply_manual_correction(
                raw_image, rotation_degrees=rotation_degrees, crop_rect=crop_rect
            )
        except ValueError as exc:
            QMessageBox.critical(self, "보정 실패", str(exc))
            return

        type_override: DocumentType | None = self.type_override_combo.currentData()
        # PRE-1: 유형만 바꾸는 요청이므로, 이미 지정된 수동 원근보정 코너(있다면)도
        # 그대로 이어간다 — `_on_crop_rotate_clicked`와 대칭적인 보존.
        corners = result.corners
        preprocess_config = self._preprocess_config_for_corners(
            corners, corrected_image.shape[:2]
        )
        if corners is not None and preprocess_config is None:
            # `_on_crop_rotate_clicked`와 동일한 이유(HIGH, code-reviewer 지적)로
            # 자르기/회전이 이어받은 이전 코너가 이 재처리 결과 이미지 크기와 맞지
            # 않으면 폐기하고 사용자에게 알린다.
            corners = None
            status_message = (
                "이전 원근보정 좌표가 새 자르기 크기와 맞지 않아 자동 검출로 "
                f"되돌렸습니다: {path.name}"
            )
        else:
            status_message = f"문서 유형을 다시 지정해 처리하는 중: {path.name}"
        self._disable_manual_correction_controls()
        self.status_label.setText(status_message)

        worker = ReprocessWorker(
            corrected_image,
            path,
            result.page_pdf_path,
            preprocess_config=preprocess_config,
            type_override=type_override,
        )
        # `_on_crop_rotate_clicked`와 동일한 이유(MEDIUM #3)로 워커 인스턴스를 클로저로
        # 고정해 넘긴다.
        worker.error_occurred.connect(
            lambda message, w=worker, p=path: self._on_reprocess_error(w, message, p)
        )
        worker.finished.connect(
            lambda w=worker: self._on_reprocess_finished(
                w, path, rotation_degrees, crop_rect, type_override, corners=corners
            )
        )
        self._reprocess_worker = worker
        # code-reviewer HIGH 지적: start() 호출 전에는 isRunning()이 항상 False이므로
        # 반드시 start() 이후에 갱신해야 한다.
        worker.start()
        self._refresh_list_editing_controls()

    def _on_perspective_correction_clicked(self) -> None:
        """PRE-1: 자동 원근보정이 실패했거나(가장 흔한 실제 케이스 — 배경 없이
        프레임을 꽉 채운 사진) 결과가 마음에 들지 않을 때, 사용자가 문서 4모서리
        좌표를 직접 지정해 다시 처리한다.

        `_on_crop_rotate_clicked`/`_on_type_override_apply_clicked`와 같은 패턴을
        쓰되, 좌표 입력 다이얼로그를 새로 연다는 점만 다르다 — 이미 저장된
        `crop_rect`/`rotation_degrees`를 그대로 raw 이미지에 재적용해 "코너를
        지정할 대상 이미지"(자르기/회전까지 끝난 상태)를 만든 뒤, 그 위에서 코너를
        입력받는다.
        """
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        path = Path(items[0].data(_PATH_ROLE))
        result = self._results_by_input.get(str(path.resolve()))
        if result is None or self._work_dir is None:
            return
        if self._is_batch_processing():
            QMessageBox.warning(
                self, "처리 중", "전체 배치 처리가 진행 중입니다. 완료 후 다시 시도하세요."
            )
            return
        if self._is_reprocessing():
            QMessageBox.warning(self, "재처리 진행 중", "이미 재처리가 진행 중입니다.")
            return

        raw_image = load_image_bgr(path)
        if raw_image is None:
            QMessageBox.critical(
                self, "이미지 읽기 실패", f"원본 이미지를 읽을 수 없습니다: {path}"
            )
            return

        # PRE-1: 원근보정 코너는 자르기/회전이 이미 적용된 이미지 좌표계를 기준으로
        # 지정해야 사용자가 보는 화면과 일치한다 — 자르기/회전 다이얼로그(Phase4-1)와
        # 동일하게 이미 저장된 값을 그대로 재적용해 그 기준 이미지를 만든다.
        rotation_degrees = result.rotation_degrees
        crop_rect = result.crop_rect
        try:
            corrected_image = apply_manual_correction(
                raw_image, rotation_degrees=rotation_degrees, crop_rect=crop_rect
            )
        except ValueError as exc:
            QMessageBox.critical(self, "보정 실패", str(exc))
            return

        height, width = corrected_image.shape[:2]
        initial_corners = result.corners
        if initial_corners is None:
            # 이전에 지정한 값이 없으면 자동 검출을 한 번 시도해 성공하면 그 좌표를
            # 초기값으로 보여준다(처음부터 다시 입력하지 않고 조정만 하면 되게).
            initial_corners = detect_document_corners(corrected_image)
        # 자동 검출도 실패하면(배경 없이 프레임을 꽉 채운 사진에서 가장 흔한 실제
        # 케이스) `PerspectiveCorrectionDialog`가 알아서 이미지 네 귀퉁이를 기본값으로
        # 채운다 — 여기서는 `None`을 그대로 넘긴다.
        dialog = PerspectiveCorrectionDialog(
            width, height, initial_corners=initial_corners, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        corners = dialog.corners()
        # PRE-1: 원근보정 코너만 다시 조정하는 요청이므로, 이 페이지에 이미 지정된
        # 문서 유형 오버라이드(있다면)는 그대로 이어간다 — 다른 두 핸들러와 동일한
        # 대칭 보존 원칙.
        type_override = result.type_override
        # LOW(code-reviewer 지적): 다른 두 핸들러와 동일하게 헬퍼를 거친다. 여기서는
        # `corners`가 항상 방금 받은 `dialog.corners()` 결과라 스핀박스 범위 제약상
        # `corrected_image` 크기를 벗어날 수 없으므로 실질적으로 폐기되지 않지만,
        # 세 진입점을 한 가지 방식으로 통일해 둔다.
        preprocess_config = self._preprocess_config_for_corners(
            corners, corrected_image.shape[:2]
        )
        if preprocess_config is None:
            corners = None
            status_message = (
                "이전 원근보정 좌표가 새 자르기 크기와 맞지 않아 자동 검출로 "
                f"되돌렸습니다: {path.name}"
            )
        else:
            status_message = f"원근 보정을 반영해 다시 처리하는 중: {path.name}"
        self._disable_manual_correction_controls()
        self.status_label.setText(status_message)

        worker = ReprocessWorker(
            corrected_image,
            path,
            result.page_pdf_path,
            preprocess_config=preprocess_config,
            type_override=type_override,
        )
        # 다른 두 핸들러와 동일한 이유(MEDIUM #3)로 워커 인스턴스를 클로저로 고정해 넘긴다.
        worker.error_occurred.connect(
            lambda message, w=worker, p=path: self._on_reprocess_error(w, message, p)
        )
        worker.finished.connect(
            lambda w=worker: self._on_reprocess_finished(
                w, path, rotation_degrees, crop_rect, type_override, corners=corners
            )
        )
        self._reprocess_worker = worker
        # code-reviewer HIGH 지적: start() 호출 전에는 isRunning()이 항상 False이므로
        # 반드시 start() 이후에 갱신해야 한다.
        worker.start()
        self._refresh_list_editing_controls()

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
        self._refresh_list_editing_controls()
        if self._is_currently_selected(input_path):
            self._refresh_manual_correction_controls(input_path)
            QMessageBox.critical(self, "재처리 오류", message)
        else:
            self.status_label.setText(f"재처리 실패: {input_path.name}: {message}")

    def _on_reprocess_finished(
        self,
        worker: ReprocessWorker,
        input_path: Path,
        rotation_degrees: int,
        crop_rect: tuple[int, int, int, int] | None,
        type_override: DocumentType | None,
        *,
        corners: np.ndarray | None = None,
    ) -> None:
        """재처리가 끝나면 `PageResult`를 갱신하고 최종 병합 PDF를 다시 만든다.

        `corners`(PRE-1, 키워드 전용, 기본값 `None`): 이번 재처리 요청에 실제로
        쓰인 수동 원근보정 코너. 기존 호출부(테스트 포함)가 위치 인자 5개만으로도
        계속 호출할 수 있도록 새 필드는 반드시 키워드 전용으로 추가한다.

        `PageResult` 데이터와 병합 PDF 갱신은 선택 여부와 무관하게 항상 수행한다.
        화면(미리보기/검수 패널) 갱신만 요청 당시 페이지가 지금도 선택돼 있을 때로
        제한한다(Phase2-4의 `_is_currently_selected` 가드 패턴).

        MEDIUM #3(code-reviewer 지적): `self._reprocess_worker`를 다시 읽는 대신
        시그널을 발생시킨 워커 인스턴스(`worker`)를 인자로 직접 받는다. `self.
        _reprocess_worker`는 그 워커가 지금도 "현재" 워커일 때만 비운다 — 그렇지
        않으면(사용자가 그 사이 같은 페이지를 다시 열어 새 재처리를 시작한
        경우) 예전 워커의 뒤늦은 `finished`가 새 워커의 참조를 지우거나, 아직
        진행 중인 새 재처리를 "끝났다"고 오인해 버튼을 잘못 다시 활성화시킬 수
        있다(`_refresh_manual_correction_controls`이 `_is_reprocessing()`도 함께 확인하므로
        버튼 자체는 이중으로 보호되지만, 참조 정리는 별도로 지켜야 한다).
        """
        if self._reprocess_worker is worker:
            self._reprocess_worker = None
        self._refresh_list_editing_controls()
        if worker.page_result is None:
            # 실패 시 `_on_reprocess_error`가 이미 메시지를 보여줬으므로 버튼 상태만 정리한다.
            if self._is_currently_selected(input_path):
                self._refresh_manual_correction_controls(input_path)
            return

        new_result = worker.page_result
        new_result.crop_rect = crop_rect
        new_result.rotation_degrees = rotation_degrees
        new_result.type_override = type_override
        new_result.corners = corners
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

        self._refresh_manual_correction_controls(input_path)
        self._refresh_processed_preview(input_path)
        self._refresh_type_review_panels(input_path)
        self.status_label.setText(f"보정을 반영해 다시 처리했습니다: {input_path.name}")
        if rebuild_error is not None:
            QMessageBox.warning(self, "PDF 재병합 실패", rebuild_error)

    def _rebuild_merged_pdf(self) -> None:
        """자르기/회전 재처리(Phase4-1)나 페이지 재정렬/삭제(Phase4-3)로 파일 목록의
        순서/구성이 바뀐 뒤, 그 순서를 그대로 유지한 채 최종 병합 PDF를 다시 만든다
        (PDF-1의 "입력 순서대로 병합"을 재사용).

        아직 처리되지 않았거나 실패한 페이지는 최초 배치 처리(`ProcessingWorker`)와
        동일하게 건너뛴다 — 부분 성공 상태에서도 병합이 가능해야 한다. 처리된
        페이지가 하나도 남지 않은 경우(Phase4-3: 처리된 페이지를 모두 삭제한 경우)는
        병합할 대상이 없으므로 이전 병합 결과를 그대로 두지 않고 명시적으로
        `None`/저장 버튼 비활성화로 되돌린다.
        """
        if self._work_dir is None:
            return
        ordered_results = [
            self._results_by_input[str(p.resolve())]
            for p in self._image_paths_in_list()
            if str(p.resolve()) in self._results_by_input
        ]
        if not ordered_results:
            self._merged_pdf_path = None
            self.save_button.setEnabled(False)
            return
        merged_pdf_path = self._work_dir / "merged.pdf"
        assemble_pdf([r.page_pdf_path for r in ordered_results], merged_pdf_path)
        self._merged_pdf_path = merged_pdf_path
        self.save_button.setEnabled(True)

    # ------------------------------------------------------------------
    # Phase4-3(PDF-2): 페이지 재정렬 / 삭제
    # ------------------------------------------------------------------

    def _on_rows_moved(self, *args: object) -> None:
        """드래그 앤 드롭으로 페이지 순서가 바뀌면 최종 병합 PDF도 새 순서로 다시 만든다.

        드래그 자체는 `_refresh_list_editing_controls()`가 워커 실행 중일 때 미리
        `NoDragDrop`으로 막아두므로 이 핸들러가 불릴 때는 항상 워커가 없는 상태일
        것이지만, 방어적으로 한 번 더 확인한다. 아직 아무 페이지도 처리되지 않았다면
        (`_merged_pdf_path is None`) 재병합할 대상이 없으므로 조용히 넘어간다.
        """
        if self._running_background_workers() or self._merged_pdf_path is None:
            return
        try:
            self._rebuild_merged_pdf()
        except Exception as exc:  # noqa: BLE001 - 파일 IO/외부 라이브러리(pymupdf) 경계
            logger.exception("페이지 재정렬 후 PDF 재병합에 실패했습니다.")
            QMessageBox.warning(self, "PDF 재병합 실패", str(exc))
            return
        self.status_label.setText("페이지 순서를 변경해 PDF를 다시 만들었습니다.")

    def _on_delete_pages_clicked(self) -> None:
        """선택된 페이지를 목록/결과 캐시에서 지우고 필요하면 최종 병합 PDF를 다시 만든다.

        `Delete`/`Backspace` 단축키와 "선택한 페이지 삭제" 버튼이 공유하는 진입점이다.
        삭제로 선택이 사라지므로(남은 항목이 자동으로 선택되지 않는다) 미리보기/검수
        패널은 항상 "선택 없음" 상태로 리셋한다 — 목록이 완전히 비면 GUI-1 이전 상태로
        자연스럽게 돌아간다.
        """
        if self._running_background_workers():
            QMessageBox.warning(
                self,
                "처리 중",
                "다른 작업(배치 처리/벡터화/재처리)이 진행 중입니다. 완료 후 다시 시도하세요.",
            )
            return
        items = self.file_list_widget.selectedItems()
        if not items:
            return

        deleted_paths = [Path(item.data(_PATH_ROLE)) for item in items]
        for item in items:
            self.file_list_widget.takeItem(self.file_list_widget.row(item))
        for path in deleted_paths:
            self._results_by_input.pop(str(path.resolve()), None)

        self._reset_preview_labels()
        self._reset_text_review_panel()
        self._refresh_list_editing_controls()

        if self.file_list_widget.count() == 0:
            self._merged_pdf_path = None
            self.save_button.setEnabled(False)
            self.status_label.setText("이미지를 추가하세요.")
            return

        try:
            self._rebuild_merged_pdf()
        except Exception as exc:  # noqa: BLE001 - 파일 IO/외부 라이브러리(pymupdf) 경계
            logger.exception("페이지 삭제 후 PDF 재병합에 실패했습니다.")
            QMessageBox.warning(self, "PDF 재병합 실패", str(exc))
            return
        remaining = self.file_list_widget.count()
        self.status_label.setText(
            f"{len(deleted_paths)}개 페이지를 삭제했습니다. (남은 {remaining}개)"
        )

    def _reset_preview_labels(self) -> None:
        """원본/처리 결과 미리보기 라벨을 초기(선택 없음) 상태로 되돌린다."""
        self.original_preview_label.setText("미리볼 이미지가 없습니다.")
        self.original_preview_label.setPixmap(QPixmap())
        self.processed_preview_label.setText("아직 처리되지 않았습니다.")
        self.processed_preview_label.setPixmap(QPixmap())

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
        self._attempt_backup(Path(save_path))

    def _attempt_backup(self, saved_pdf_path: Path) -> None:
        """BKP-1/BKP-3: 로컬 저장이 끝난 뒤에만 호출되는 백업 훅.

        백업이 꺼져 있으면 아무 것도 하지 않고 즉시 반환한다(오프라인 보장).
        켜져 있을 때도 `upload_pdf`(현재는 Phase5-2가 채울 no-op 스텁)를
        try/except로 감싸, 백업이 실패하거나 예외를 던져도 이미 완료된 로컬
        저장 결과나 GUI 반응성에 전혀 영향을 주지 않게 한다 — BKP-1 수용 기준의
        핵심("백업 실패가 로컬 저장 결과에 영향을 주지 않는다").

        주의: 지금은 `upload_pdf`가 즉시 반환하는 no-op이라 동기 호출이어도
        무해하다. Phase5-2에서 실제 네트워크 호출을 채워 넣을 때는 GUI 스레드를
        블로킹하지 않도록 별도 QThread(예: `ProcessingWorker`/`VectorizeWorker`와
        같은 패턴)로 옮기는 것을 고려해야 한다.
        """
        if not self._backup_settings.is_backup_enabled():
            return
        try:
            upload_pdf(saved_pdf_path)
        except Exception:  # noqa: BLE001 - 백업 실패가 로컬 저장 결과에 영향을 주면 안 되는 경계
            logger.exception(
                "백업 업로드 중 오류가 발생했습니다 (로컬 저장 결과에는 영향 없음): %s",
                saved_pdf_path,
            )

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
