"""§9 Phase4 완료 검증: "여러 유형이 섞인 입력 세트"로 전체 워크플로우 end-to-end.

`docs/prd.md` §9: "Phase 4 완료 시: GUI에서 여러 유형이 섞인 입력 세트로 전체
워크플로우(입력→검수→조립→저장)를 수행." `tests/gui/test_e2e_phase2.py`/
`tests/gui/test_e2e_phase3.py`가 이미 단일 유형(도형/악보) 샘플로 같은 패턴의
end-to-end를 검증해뒀으므로, 여기서는 텍스트+도형이 섞인 입력 세트 하나로
실제 `MainWindow`를 통해 입력(GUI-1) → 백그라운드 처리(전처리+자동분류+라우팅,
QThread) → 문서 유형별 검수 UI 전환(GUI-3, Phase4-2) → Phase4에서 새로 추가된
기능(수동 유형 오버라이드 재처리 Phase4-4, 페이지 삭제 Phase4-3) → 조립 →
저장(GUI-4)까지 하나의 흐름으로 잇는다.

개별 Phase4 기능은 이미 다음 테스트들이 각자 회귀 검증하므로, 여기서는 그
전체가 "혼합 입력" 시나리오 하나로 실제로 맞물려 돌아가는지에 집중한다:
- `tests/gui/test_crop_rotate_guards.py` (워커 실행 상태에 따른 버튼/가드 로직)
- `tests/gui/test_crop_rotate_reprocess.py` (자르기/회전 재처리 실제 파이프라인)
- `tests/gui/test_page_reorder_delete.py` (재정렬/삭제 자체의 세부 동작)
- `tests/gui/test_worker_routing.py` (`ProcessingWorker`/`ReprocessWorker` 라우팅)
- `tests/router/test_classifier.py` (RT-1 자동 분류 + 수동 오버라이드가 휴리스틱을
  무시하고 그 값을 그대로 반환하는지)

수동 오버라이드 시나리오는 실제 업무 동기가 있다 — 최근 Phase4-4에서 표가
DIAGRAM으로 오탐되는 사례를 이 UI로 구제하기로 결정했으므로, 자동 분류가
DIAGRAM으로 판정한 페이지를 사용자가 TEXT로 되돌려 재처리하는 흐름을 GUI
레벨에서 실제 파이프라인 끝까지 검증해둔다(RT-1 "자동 추정 + 수동 오버라이드").

Tesseract/Ghostscript/qpdf가 이 머신에 설치돼 있어야 실제 텍스트 재처리
파이프라인을 끝까지 태울 수 있으므로, `tests/gui/test_crop_rotate_reprocess.py`와
동일하게 없으면 skip한다.
"""

from __future__ import annotations

import shutil

import cv2
import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.gui.main_window import MainWindow
from app.router.classifier import DocumentType

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None

pytestmark = pytest.mark.skipif(
    not (_TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE),
    reason="tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다.",
)


def test_phase4_end_to_end_mixed_input_with_manual_override_and_page_delete(
    qtbot, tmp_path, monkeypatch, synthetic_text_photo, synthetic_diagram_photo
):
    """PRD §9 Phase4 수용 기준: 텍스트+도형 혼합 입력 → 입력→검수→보정→조립→저장 전체 흐름.

    - 입력: 텍스트 샘플 1장 + 도형 샘플 1장을 함께 추가한다 (GUI-1, "여러 유형이
      섞인 입력 세트").
    - 처리: `_start_processing` 후 `processing_completed`를 대기 (백그라운드 QThread).
    - 자동 분류(RT-1): 텍스트 페이지는 TEXT로, 도형 페이지는 DIAGRAM으로 분류돼야
      한다 — 두 페이지 모두 처음부터 성공해 병합 PDF가 2페이지여야 한다.
    - 검수 UI 전환(GUI-3, Phase4-2): 선택된 페이지의 `document_type`에 따라
      `review_stack`이 텍스트/도형 패널을 정확히 전환해야 한다.
    - 수동 오버라이드 재처리(RT-1, Phase4-4): 도형으로 자동 분류된 페이지를
      사용자가 "텍스트"로 강제 지정해 다시 처리하면, 실제 파이프라인(OCR 포함)이
      다시 돌아 `PageResult.document_type`/`type_override`가 갱신되고 검수 UI도
      텍스트 패널로 전환돼야 한다. 병합 PDF도 여전히 2페이지를 유지해야 한다.
    - 페이지 삭제(PDF-2, Phase4-3): 원래 텍스트였던 첫 페이지를 삭제하면 목록/결과
      캐시에서 제거되고, 남은 페이지(오버라이드된 옛 도형 페이지)만으로 병합 PDF가
      다시 만들어져야 한다.
    - 저장(GUI-4): `QFileDialog.getSaveFileName`을 monkeypatch해 최종 PDF가 실제로
      저장되고, 그 PDF가 삭제/오버라이드 이후 상태(페이지 수 1장)를 정확히
      반영해야 한다.
    """
    text_path = tmp_path / "page1_text.png"
    diagram_path = tmp_path / "page2_diagram.png"
    cv2.imwrite(str(text_path), synthetic_text_photo.photo)
    cv2.imwrite(str(diagram_path), synthetic_diagram_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)

    # 모달 다이얼로그는 이벤트 루프를 막으므로 전부 몽키패치해 호출 여부/내용만 기록한다.
    shown_messages: list[str] = []
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.information",
        lambda *args, **kwargs: shown_messages.append(args[-1]),
    )
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: shown_messages.append(args[-1]),
    )
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.critical",
        lambda *args, **kwargs: shown_messages.append(args[-1]),
    )
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    # --- 입력 (GUI-1, 혼합 입력 세트) ---------------------------------------
    window._add_image_paths([text_path, diagram_path])
    assert window._image_paths_in_list() == [text_path.resolve(), diagram_path.resolve()]

    # --- 처리 (전처리 + 자동분류 + 라우팅, 백그라운드 QThread) -----------------
    with qtbot.waitSignal(window.processing_completed, timeout=180000):
        window._start_processing()
        # 워커 스레드가 즉시 시작되어 입력 컨트롤이 비활성화된 상태로 곧바로
        # 돌아와야 한다(UI가 파이프라인 완료까지 블로킹되지 않음을 보여준다).
        assert window.process_button.isEnabled() is False

    assert shown_messages == []  # 두 페이지 모두 정상 처리되어 경고/오류 팝업이 없어야 한다.
    assert window.save_button.isEnabled() is True
    assert window._merged_pdf_path is not None
    assert window._merged_pdf_path.exists()

    text_result = window._results_by_input[str(text_path.resolve())]
    diagram_result = window._results_by_input[str(diagram_path.resolve())]
    # --- 자동 분류 (RT-1) --------------------------------------------------
    assert text_result.document_type == DocumentType.TEXT
    assert diagram_result.document_type == DocumentType.DIAGRAM

    with pymupdf.open(window._merged_pdf_path) as doc:
        assert doc.page_count == 2

    # --- 검수 UI 전환 (GUI-3, Phase4-2) -------------------------------------
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert window.review_stack.currentWidget() is window._text_review_page
    assert window.text_review_edit.isEnabled() is True

    window.file_list_widget.setCurrentItem(window.file_list_widget.item(1))
    assert window.review_stack.currentWidget() is window._diagram_review_page
    assert window.text_review_edit.isEnabled() is False
    assert window.vectorize_button.isEnabled() is True
    assert window.type_override_apply_button.isEnabled() is True

    # --- 수동 오버라이드 재처리 (RT-1, Phase4-4): DIAGRAM → TEXT로 되돌림 -------
    # (표→DIAGRAM 오탐 시나리오처럼, 자동 분류 결과를 사람이 직접 바로잡는 대표 흐름)
    text_override_index = window.type_override_combo.findData(DocumentType.TEXT)
    assert text_override_index >= 0
    window.type_override_combo.setCurrentIndex(text_override_index)

    qtbot.mouseClick(window.type_override_apply_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._reprocess_worker is None, timeout=120000)

    overridden_result = window._results_by_input[str(diagram_path.resolve())]
    assert overridden_result is not diagram_result
    assert overridden_result.document_type == DocumentType.TEXT
    assert overridden_result.type_override == DocumentType.TEXT
    # OCR을 실제로 실행했는지가 중요하지, 도형 이미지에서 인식된 문자열 내용의
    # 정확도는 단정하지 않는다(무거운 ML/OCR 컴포넌트 테스트 전략).
    assert overridden_result.text is not None

    # 재처리 요청 당시 선택돼 있던 페이지가 그대로 선택돼 있으므로 화면도 갱신돼야 한다.
    assert window.review_stack.currentWidget() is window._text_review_page
    assert window.text_review_edit.isEnabled() is True

    # 유형만 바뀌었을 뿐 페이지 수는 그대로 유지돼야 한다(PDF-1 재조립).
    with pymupdf.open(window._merged_pdf_path) as doc:
        assert doc.page_count == 2

    # --- 페이지 삭제 (PDF-2, Phase4-3): 원래 텍스트였던 첫 페이지를 제거 -----------
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert window.delete_page_button.isEnabled() is True
    window._on_delete_pages_clicked()

    assert window.file_list_widget.count() == 1
    assert str(text_path.resolve()) not in window._results_by_input
    assert str(diagram_path.resolve()) in window._results_by_input

    with pymupdf.open(window._merged_pdf_path) as doc:
        assert doc.page_count == 1

    # --- 저장 (GUI-4) -------------------------------------------------------
    destination = tmp_path / "phase4_e2e_output.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )
    window._on_save_clicked()

    assert destination.exists()
    with pymupdf.open(destination) as doc:
        # 삭제된 페이지를 제외한, 오버라이드로 TEXT가 된 옛 도형 페이지 1장만 남아야 한다.
        assert doc.page_count == 1
