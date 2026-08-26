"""§9 Phase2 완료 검증(task `d2d67738`): 도형 샘플 1장 → GUI 전체 흐름, end-to-end.

`docs/prd.md` §9: "Phase 2/3 완료 시: 각각 도형/악보 샘플로 동일한 end-to-end
확인." Phase1-7(`tests/gui/test_e2e_phase1.py`)이 텍스트 샘플로 이미 이 패턴을
구현해뒀으므로, 여기서는 도형(diagram) 샘플로 동일한 흐름을 검증한다: 실제
`MainWindow`를 통해 입력(GUI-1) → 백그라운드 처리(전처리+자동분류+라우팅,
QThread) → 미리보기(GUI-2) → 도형 전용 검수 UI(GUI-3, DIA-3) → 벡터화
(DIA-2/DIA-3) → 저장(GUI-4)까지 한 번에 잇는다.

악보(score) 쪽 end-to-end는 SCR-2/SCR-3/GUI 연결이 아직 없고 이 머신에
MuseScore도 설치돼 있지 않으므로 Phase3 완료 후(Phase3-5)에 별도로 다룬다
(이 파일의 범위 밖).

개별 컴포넌트는 이미 다음 테스트들이 검증하므로, 여기서는 그 전체가 사용자
흐름 하나로 실제로 이어지는지에 집중한다:
- `tests/router/test_classifier.py` (RT-1 자동 분류)
- `tests/gui/test_worker_routing.py` (ProcessingWorker의 도형 라우팅)
- `tests/processors/test_diagram.py` (DIA-1/DIA-2 처리기 자체)
- `tests/gui/test_diagram_routing.py` (도형 페이지에 대한 MainWindow UI 반응)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import cv2
import pymupdf
from PySide6.QtCore import Qt

from app.gui.main_window import MainWindow
from app.processors.diagram import VECTORIZATION_DISCLAIMER
from app.router.classifier import DocumentType


def test_phase2_end_to_end_distorted_diagram_photo_to_pdf_and_svg(
    qtbot, tmp_path, monkeypatch, synthetic_diagram_photo
):
    """PRD §9 Phase2 수용 기준: 왜곡·저해상도 도형 샘플 1장 → 입력→검수→벡터화→저장 전체 흐름.

    - `synthetic_diagram_photo`: 원근왜곡+조명그라디언트+카메라노이즈+다운샘플이 모두
      합성 적용된 "왜곡·저해상도 도형 샘플".
    - 입력: `_add_image_paths`로 GUI 파일 목록에 추가 (GUI-1).
    - 처리: `_start_processing` 후 `processing_completed`를 대기 (백그라운드 QThread).
      `tesseract`/`ghostscript`/`qpdf` 없이도 도형 경로는 OCRmyPDF를 타지 않으므로
      (Phase1 텍스트 e2e와 달리) skip 조건이 필요 없다.
    - 자동 분류: `PageResult.document_type`이 실제로 `DocumentType.DIAGRAM`으로
      분류돼야 한다(RT-1). `tests/gui/test_worker_routing.py`가 이미 이 fixture로
      안정적인 DIAGRAM 분류를 확인했으므로, 여기서는 그 결과를 그대로 검증
      대상으로 삼는다(수동 override 없이 자동 분류 경로 그대로).
    - 미리보기: 원본/처리 결과 QPixmap이 모두 유효해야 함 (GUI-2).
    - 도형 전용 검수 UI: 도형 페이지 선택 시 텍스트 검수 패널이 비활성화되고
      전용 안내 문구가 뜨며, 벡터화 버튼이 활성화돼야 함 (GUI-3, DIA-3).
    - 벡터화: "SVG로 벡터화" 버튼 클릭 → `VectorizeWorker` 완료 대기 → 유효한
      SVG가 생성되고 한계 고지 문구가 라벨에 노출돼야 함 (DIA-2/DIA-3).
    - 저장: `QFileDialog.getSaveFileName`을 monkeypatch해 사용자가 지정한 경로에
      PDF가 실제로 저장되고 (GUI-4), 그 PDF를 pymupdf로 다시 열었을 때 페이지 수가
      맞고 텍스트 레이어가 없어야 함(도형은 OCR 대상이 아니므로 TXT-2와 대비됨).
    """
    image_path = tmp_path / "distorted_low_res_diagram.png"
    cv2.imwrite(str(image_path), synthetic_diagram_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)

    # --- 입력 (GUI-1) ---------------------------------------------------
    window._add_image_paths([image_path])
    assert window._image_paths_in_list() == [image_path.resolve()]

    # --- 처리 (전처리 + 자동분류 + 도형 라우팅, 백그라운드 QThread) ----------
    with qtbot.waitSignal(window.processing_completed, timeout=180000):
        window._start_processing()
        # 워커 스레드가 즉시 시작되어 입력 컨트롤이 비활성화된 상태로 곧바로
        # 돌아와야 한다(UI가 파이프라인 완료까지 블로킹되지 않음을 보여준다).
        assert window.process_button.isEnabled() is False

    assert window.save_button.isEnabled() is True
    assert window._merged_pdf_path is not None
    assert window._merged_pdf_path.exists()

    result = window._results_by_input[str(image_path.resolve())]
    # --- 자동 분류 (RT-1) --------------------------------------------------
    assert result.document_type == DocumentType.DIAGRAM
    assert result.text is None  # 도형 페이지는 OCR 텍스트가 없어야 한다.
    assert result.sharpened_image is not None

    # --- 미리보기 (GUI-2) -------------------------------------------------
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert not window.original_preview_label.pixmap().isNull()
    assert not window.processed_preview_label.pixmap().isNull()

    # --- 도형 전용 검수 UI (GUI-3, DIA-3) -----------------------------------
    assert window.text_review_edit.isEnabled() is False
    assert (
        window.text_review_edit.placeholderText()
        == "이 페이지는 도형으로 분류되어 텍스트 검수 대상이 아닙니다."
    )
    assert window.vectorize_button.isEnabled() is True

    # --- 벡터화 (DIA-2/DIA-3) ------------------------------------------------
    shown_messages: list[str] = []
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.information",
        lambda *args, **kwargs: shown_messages.append(args[-1]),
    )

    qtbot.mouseClick(window.vectorize_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: result.svg_path is not None, timeout=30000)

    assert result.svg_path.exists()
    assert result.vectorization_disclaimer == VECTORIZATION_DISCLAIMER
    root = ET.fromstring(result.svg_path.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    assert root.attrib.get("width")
    assert root.attrib.get("height")

    assert shown_messages and shown_messages[-1] == VECTORIZATION_DISCLAIMER
    assert window.vectorization_disclaimer_label.text() == VECTORIZATION_DISCLAIMER

    # --- 저장 (GUI-4) -------------------------------------------------------
    destination = tmp_path / "phase2_e2e_output.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )
    window._on_save_clicked()

    assert destination.exists()
    with pymupdf.open(destination) as doc:
        assert doc.page_count == 1
        pdf_text = doc[0].get_text()

    # 도형은 OCR 텍스트 레이어가 없는 게 정상이다(TXT-2와 달리 DIA-1은 텍스트 레이어를 만들지 않음).
    assert pdf_text.strip() == ""
