"""§9 Phase1 완료 검증(task `185b6d07`): 왜곡·저해상도 샘플 1장 → 검색 가능한 PDF, end-to-end.

`docs/prd.md` §9: "Phase 1 완료 시: 왜곡·저해상도 샘플 이미지 1장을 입력해 검색 가능한
PDF가 생성되는지 end-to-end로 확인." 이를 위해 실제 `MainWindow`를 통해
입력(GUI-1) → 백그라운드 처리(전처리+OCR, QThread) → 미리보기(GUI-2) → 텍스트
검수(TXT-3) → 저장(GUI-4)까지 한 번에 잇는다. 개별 컴포넌트는 이미
`tests/processors/test_text.py`, `tests/gui/test_worker.py`,
`tests/gui/test_main_window.py`가 검증하므로, 여기서는 그 전체가 사용자 흐름
하나로 실제로 이어지는지에 집중한다.
"""

from __future__ import annotations

import difflib
import shutil

import cv2
import pymupdf
import pytest

from app.gui.main_window import MainWindow

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None
_PIPELINE_AVAILABLE = _TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE

_PIPELINE_SKIP_REASON = "tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다."


def _similarity_ignoring_whitespace(candidate: str, expected: str) -> float:
    """공백/줄바꿈 차이를 무시한 유사도. `tests/processors/test_text.py`와 동일한 패턴.

    pymupdf가 텍스트 레이어를 재추출할 때 줄바꿈 위치를 원문과 다르게 재구성할 수
    있어(내용이 달라진 게 아니라 추출 휴리스틱 차이), 공백을 제거하고 비교한다.
    """
    a = "".join(candidate.split())
    b = "".join(expected.split())
    return difflib.SequenceMatcher(None, a, b).ratio()


@pytest.mark.skipif(not _PIPELINE_AVAILABLE, reason=_PIPELINE_SKIP_REASON)
def test_phase1_end_to_end_distorted_photo_to_searchable_pdf(
    qtbot, tmp_path, monkeypatch, synthetic_text_photo
):
    """PRD §9 Phase1 수용 기준: 왜곡·저해상도 샘플 1장 → 입력→검수→조립→저장 전체 흐름.

    - `synthetic_text_photo`: 원근왜곡+조명그라디언트+카메라노이즈+다운샘플이 모두
      합성 적용된 "왜곡·저해상도 샘플".
    - 입력: `_add_image_paths`로 GUI 파일 목록에 추가 (GUI-1).
    - 처리: `_start_processing` 후 `processing_completed`를 대기 (백그라운드 QThread).
    - 미리보기: 원본/처리 결과 QPixmap이 모두 유효해야 함 (GUI-2).
    - 검수: `text_review_edit`에 OCR 텍스트가 채워지고 원문과 유사해야 함 (TXT-3).
    - 저장: `QFileDialog.getSaveFileName`을 monkeypatch해 사용자가 지정한 경로에 PDF가
      실제로 저장되고 (GUI-4), 그 PDF를 pymupdf로 다시 열었을 때 텍스트 레이어가
      원문과 충분히 유사해야 함 (TXT-2, "검색 가능한 PDF").
    """
    image_path = tmp_path / "distorted_low_res_page.png"
    cv2.imwrite(str(image_path), synthetic_text_photo.photo)
    expected_text = synthetic_text_photo.text
    assert expected_text  # 텍스트 fixture이므로 원문이 반드시 있어야 함

    window = MainWindow()
    qtbot.addWidget(window)

    # --- 입력 (GUI-1) ---------------------------------------------------
    window._add_image_paths([image_path])
    assert window._image_paths_in_list() == [image_path.resolve()]

    # --- 처리 (전처리 + OCR, 백그라운드 QThread) --------------------------
    with qtbot.waitSignal(window.processing_completed, timeout=180000):
        window._start_processing()
        # 워커 스레드가 즉시 시작되어 입력 컨트롤이 비활성화된 상태로 곧바로
        # 돌아와야 한다(UI가 파이프라인 완료까지 블로킹되지 않음을 보여준다).
        assert window.process_button.isEnabled() is False

    assert window.save_button.isEnabled() is True
    assert window._merged_pdf_path is not None
    assert window._merged_pdf_path.exists()

    result = window._results_by_input[str(image_path.resolve())]
    assert result.text.strip() != ""

    # --- 미리보기 (GUI-2) -------------------------------------------------
    window.file_list_widget.setCurrentItem(window.file_list_widget.item(0))
    assert not window.original_preview_label.pixmap().isNull()
    assert not window.processed_preview_label.pixmap().isNull()

    # --- 텍스트 검수 (TXT-3) -----------------------------------------------
    assert window.text_review_edit.isEnabled() is True
    reviewed_text = window.text_review_edit.toPlainText()
    assert reviewed_text == result.text
    assert reviewed_text.strip() != ""
    # 왜곡·저해상도 샘플에서도 인식 결과가 원문과 충분히 유사해야 "검수"가 의미 있다.
    assert _similarity_ignoring_whitespace(reviewed_text, expected_text) > 0.7

    # --- 저장 (GUI-4) -------------------------------------------------------
    destination = tmp_path / "phase1_e2e_output.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )
    window._on_save_clicked()

    assert destination.exists()
    with pymupdf.open(destination) as doc:
        assert doc.page_count == 1
        pdf_text = doc[0].get_text()

    # --- 검색 가능한 PDF (TXT-2) 검증 --------------------------------------
    assert pdf_text.strip() != ""
    assert _similarity_ignoring_whitespace(pdf_text, expected_text) > 0.7
    # 원문 중 눈에 잘 띄는 한 단어가 실제로 텍스트 레이어에서 검색돼야 한다.
    assert "quick" in pdf_text.lower()
