"""§9 Phase3 완료 검증(task `96bc862b`): 악보 샘플 1장 → GUI 전체 흐름, end-to-end.

`docs/prd.md` §9: "Phase 2/3 완료 시: 각각 도형/악보 샘플로 동일한 end-to-end
확인." `tests/gui/test_e2e_phase2.py`가 도형 샘플로 이미 이 패턴을 구현해뒀으므로,
여기서는 악보(score) 샘플로 동일한 흐름을 검증한다: 실제 `MainWindow`를 통해
입력(GUI-1) → 백그라운드 처리(전처리+자동분류+라우팅, QThread) → 미리보기(GUI-2)
→ 악보 전용 검수 UI(GUI-3, SCR-3) → 저장(GUI-4)까지 한 번에 잇는다.

이 개발 머신에는 oemer OMR 체크포인트(수백MB, `_checkpoint_path()`가 가리키는
`unet_big/model.onnx`)가 의도적으로 내려받아있지 않으므로(`docs/roadmap.md`
Phase3-1 참고), 정식 happy-path E2E(`test_phase3_end_to_end_...`)는 체크포인트가
있는 다른 머신/CI에서만 실제로 실행되고 이 머신에서는 skip된다
(`tests/processors/test_score.py`가 이미 세운 관행을 그대로 따른다).

그것만으로는 이 머신에서 Phase3 GUI 흐름이 전혀 검증되지 않으므로,
`test_phase3_gracefully_isolates_score_page_when_checkpoint_missing`을 별도로
두어 "체크포인트가 없는 개발 환경에서 앱이 우아하게 실패하는가"를 실제로
증명한다 — 텍스트 샘플과 악보 샘플을 함께 입력해 부분 성공(텍스트는 성공,
악보는 `ScoreModelUnavailableError`로 격리) 시나리오를 실제 `MainWindow`로
끝까지 돌려본다.

개별 컴포넌트는 이미 다음 테스트들이 검증하므로, 여기서는 그 전체가 사용자
흐름 하나로 실제로 이어지는지에 집중한다:
- `tests/router/test_classifier.py` (RT-1 자동 분류, 오선 검출로 SCORE 판정)
- `tests/gui/test_worker_routing.py` (`ProcessingWorker`의 악보 라우팅 및 페이지
  단위 실패 격리)
- `tests/processors/test_score.py` (SCR-1/SCR-2 처리기 자체, 체크포인트 부재 시
  `ScoreModelUnavailableError` 검증)
- `tests/gui/test_score_routing.py` (악보 페이지에 대한 `MainWindow` UI 반응,
  `PageResult`를 직접 주입한 순수 UI 스모크 테스트)
"""

from __future__ import annotations

from pathlib import Path

import cv2
import pymupdf
import pytest
from PySide6.QtCore import Qt

from app.gui.main_window import MainWindow
from app.processors.score import _checkpoint_path
from app.router.classifier import DocumentType


def test_phase3_end_to_end_distorted_score_photo_to_pdf(
    qtbot, tmp_path, monkeypatch, synthetic_score_photo
):
    """PRD §9 Phase3 수용 기준: 왜곡·저해상도 악보 샘플 1장 → 입력→검수→저장 전체 흐름.

    - `synthetic_score_photo`: 원근왜곡+조명그라디언트+카메라노이즈+다운샘플이 모두
      합성 적용된 "왜곡·저해상도 악보 샘플"(MuseScore로 실제 엔그레이빙 렌더링).
    - 입력: `_add_image_paths`로 GUI 파일 목록에 추가 (GUI-1).
    - 처리: `_start_processing` 후 `processing_completed`를 대기 (백그라운드 QThread).
    - 자동 분류: `PageResult.document_type`이 실제로 `DocumentType.SCORE`로
      분류돼야 한다(RT-1, 오선 검출 휴리스틱). 수동 override 없이 자동 분류
      경로 그대로 검증한다.
    - 미리보기: 원본/처리 결과 QPixmap이 모두 유효해야 함 (GUI-2).
    - 악보 전용 검수 UI: 악보 페이지 선택 시 텍스트 검수 패널이 비활성화되고
      전용 안내 문구가 뜨며, "MuseScore에서 열기" 버튼이 활성화돼야 함
      (GUI-3, SCR-3 UI). 실제로 MuseScore GUI를 띄우면 자동화 테스트에서
      제어할 수 없는 외부 앱 창이 열리므로, 버튼을 클릭하지 않고 활성화
      조건만 확인한다(클릭 동작 자체는 `tests/gui/test_score_routing.py`가
      `open_score_in_external_editor`를 몽키패치해 이미 검증함).
    - 저장: `QFileDialog.getSaveFileName`을 monkeypatch해 사용자가 지정한 경로에
      PDF가 실제로 저장되고 (GUI-4), 그 PDF를 pymupdf로 다시 열었을 때 페이지 수가
      맞고 텍스트 레이어가 없어야 함(악보는 OCR 대상이 아니므로 TXT-2와 대비됨).

    이 개발 머신에는 oemer 체크포인트가 준비되어 있지 않아 실제 OMR 인식을 실행할
    수 없으므로 skip한다 — 체크포인트를 준비해둔 머신/CI에서 실제로 끝까지 실행된다.
    """
    if not _checkpoint_path().exists():
        pytest.skip("oemer 체크포인트가 준비되어 있지 않아 실제 OMR 인식을 실행할 수 없습니다.")

    image_path = tmp_path / "distorted_low_res_score.png"
    cv2.imwrite(str(image_path), synthetic_score_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)

    # --- 입력 (GUI-1) ---------------------------------------------------
    window._add_image_paths([image_path])
    assert window._image_paths_in_list() == [image_path.resolve()]

    # --- 처리 (전처리 + 자동분류 + 악보 라우팅, 백그라운드 QThread) ----------
    with qtbot.waitSignal(window.processing_completed, timeout=300000):
        window._start_processing()
        # 워커 스레드가 즉시 시작되어 입력 컨트롤이 비활성화된 상태로 곧바로
        # 돌아와야 한다(UI가 파이프라인 완료까지 블로킹되지 않음을 보여준다).
        assert window.process_button.isEnabled() is False

    assert window.save_button.isEnabled() is True
    assert window._merged_pdf_path is not None
    assert window._merged_pdf_path.exists()

    result = window._results_by_input[str(image_path.resolve())]
    # --- 자동 분류 (RT-1) --------------------------------------------------
    assert result.document_type == DocumentType.SCORE
    assert result.text is None  # 악보 페이지는 OCR 텍스트가 없어야 한다.
    assert result.musicxml_path is not None
    assert result.musicxml_path.exists()

    # --- 미리보기 (GUI-2) -------------------------------------------------
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert not window.original_preview_label.pixmap().isNull()
    assert not window.processed_preview_label.pixmap().isNull()

    # --- 악보 전용 검수 UI (GUI-3, SCR-3) -----------------------------------
    assert window.text_review_edit.isEnabled() is False
    assert (
        window.text_review_edit.placeholderText()
        == "이 페이지는 악보로 분류되어 텍스트 검수 대상이 아닙니다."
    )
    assert window.open_in_musescore_button.isEnabled() is True

    # --- 저장 (GUI-4) -------------------------------------------------------
    destination = tmp_path / "phase3_e2e_output.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )
    window._on_save_clicked()

    assert destination.exists()
    with pymupdf.open(destination) as doc:
        assert doc.page_count == 1
        pdf_text = doc[0].get_text()

    # 악보는 OCR 텍스트 레이어가 없는 게 정상이다(TXT-2와 달리 SCR-1/2는 텍스트
    # 레이어를 만들지 않음).
    assert pdf_text.strip() == ""


def test_phase3_gracefully_isolates_score_page_when_checkpoint_missing(
    qtbot, tmp_path, monkeypatch, synthetic_text_photo, synthetic_score_photo
):
    """이 개발 머신 현실("oemer 체크포인트 없음")에서 앱이 우아하게 실패하는지 실증한다.

    체크포인트가 없으면 `recognize_score`가 `ScoreModelUnavailableError`를 던지고
    (`tests/processors/test_score.py`), `ProcessingWorker`는 이를 페이지 단위
    실패로 격리해 나머지 페이지는 계속 처리한다(`tests/gui/test_worker_routing.py`
    `test_processing_worker_merges_successful_pages_when_one_page_misclassified_as_score`).
    이 테스트는 그 두 계약이 실제 `MainWindow`를 통해 크래시 없이 끝까지 이어지는지
    end-to-end로 증명한다: 텍스트 샘플 1장 + 악보 샘플 1장을 함께 입력하면,
    텍스트 페이지는 성공하고 악보 페이지만 실패해 부분 성공(GUI-4 저장 가능)
    상태가 돼야 한다.

    체크포인트가 이미 준비된 머신에서는 이 실패 시나리오 자체가 재현되지 않으므로
    skip한다.
    """
    if _checkpoint_path().exists():
        pytest.skip("체크포인트가 이미 준비되어 있어 부재 시 격리 동작을 검증할 수 없습니다")

    text_path = tmp_path / "page1_text.png"
    score_path = tmp_path / "page2_score.png"
    cv2.imwrite(str(text_path), synthetic_text_photo.photo)
    cv2.imwrite(str(score_path), synthetic_score_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)

    # QMessageBox는 실제로 띄우면 모달로 이벤트 루프를 막으므로, 호출 여부/내용만
    # 기록하도록 몽키패치한다(부분 실패는 warning, 완전 실패라면 critical이어야
    # 하므로 둘 다 감시해 어느 쪽이 실제로 호출되는지 구분한다).
    warning_messages: list[str] = []
    critical_messages: list[str] = []
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: warning_messages.append(args[-1]),
    )
    monkeypatch.setattr(
        "app.gui.main_window.QMessageBox.critical",
        lambda *args, **kwargs: critical_messages.append(args[-1]),
    )

    # --- 입력 (GUI-1) ---------------------------------------------------
    window._add_image_paths([text_path, score_path])
    assert window._image_paths_in_list() == [text_path.resolve(), score_path.resolve()]

    # --- 처리 (전처리 + 자동분류 + 라우팅, 백그라운드 QThread) ----------------
    with qtbot.waitSignal(window.processing_completed, timeout=180000):
        window._start_processing()
        assert window.process_button.isEnabled() is False

    # --- 크래시 없이 부분 성공으로 마무리돼야 한다 ----------------------------
    assert window.process_button.isEnabled() is True  # 입력 컨트롤이 복구됨
    assert window.save_button.isEnabled() is True
    assert window._merged_pdf_path is not None
    assert window._merged_pdf_path.exists()

    # 완전 실패가 아니라 부분 실패이므로 warning만 뜨고 critical은 뜨지 않아야 한다.
    assert critical_messages == []
    assert len(warning_messages) == 1
    assert "1장" in warning_messages[0]
    assert "oemer" in warning_messages[0] or "체크포인트" in warning_messages[0]
    assert "1/2" in window.status_label.text() or "1장 실패" in window.status_label.text()

    # 텍스트 페이지만 성공해 결과에 남아야 한다.
    assert str(text_path.resolve()) in window._results_by_input
    assert str(score_path.resolve()) not in window._results_by_input
    text_result = window._results_by_input[str(text_path.resolve())]
    assert text_result.document_type == DocumentType.TEXT
    assert text_result.text is not None and text_result.text.strip() != ""

    # 성공한 텍스트 페이지 1장만으로 병합 PDF가 만들어져 저장할 수 있어야 한다.
    with pymupdf.open(window._merged_pdf_path) as doc:
        assert doc.page_count == 1

    # 실패한 악보 페이지를 선택해도 크래시하지 않고 "아직 처리되지 않았습니다"로
    # 안내해야 한다(성공/실패와 무관하게 목록에서 계속 선택 가능해야 함).
    assert window.file_list_widget.count() == 2
    score_item = window.file_list_widget.item(1)
    assert Path(score_item.data(Qt.ItemDataRole.UserRole)) == score_path.resolve()
    window.file_list_widget.setCurrentItem(score_item)
    assert window.text_review_edit.placeholderText() == "아직 처리되지 않았습니다."
    assert window.open_in_musescore_button.isEnabled() is False

    # --- 저장 (GUI-4): 부분 성공이어도 저장 자체는 정상 동작해야 한다 ------------
    destination = tmp_path / "phase3_partial_e2e_output.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )
    window._on_save_clicked()

    assert destination.exists()
    with pymupdf.open(destination) as doc:
        assert doc.page_count == 1
