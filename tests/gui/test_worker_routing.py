"""Phase2-4(GUI에 도형 처리 경로 연결) 수용 기준 검증: `ProcessingWorker`의 자동 라우팅.

RT-1(자동 분류)/RT-2(위임) 자체는 `tests/router/test_classifier.py`,
`tests/router/test_dispatch.py`에서 이미 검증하므로, 여기서는 `ProcessingWorker`가
그 결과를 받아 올바른 `PageResult`(도형은 `text=None`+`sharpened_image` 채움,
텍스트는 `text` 채움)로 변환하고, 텍스트/도형이 섞인 배치도 각 페이지를 순서대로
올바르게 처리하는지 스모크 수준으로 확인한다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import cv2
import pymupdf
import pytest

from app.gui.worker import ProcessingWorker
from app.router.classifier import DocumentType

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None
_TEXT_PIPELINE_AVAILABLE = _TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE
_TEXT_PIPELINE_SKIP_REASON = "tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다."


def test_processing_worker_routes_diagram_photo_without_ocr(
    qtbot, tmp_path, synthetic_diagram_photo
):
    """도형 사진은 OCR 없이 도형 처리기로 라우팅되어야 한다(Tesseract 불필요)."""
    image_path = tmp_path / "diagram.png"
    cv2.imwrite(str(image_path), synthetic_diagram_photo.photo)
    work_dir = tmp_path / "work"

    worker = ProcessingWorker([image_path], work_dir)

    with qtbot.waitSignal(worker.finished, timeout=60000):
        worker.start()

    assert worker.merged_pdf_path is not None
    assert len(worker.page_results) == 1
    page_result = worker.page_results[0]
    assert page_result.document_type == DocumentType.DIAGRAM
    assert page_result.text is None
    assert page_result.sharpened_image is not None
    assert page_result.svg_path is None  # DIA-2: 자동 벡터화는 실행되지 않는다.


@pytest.mark.skipif(not _TEXT_PIPELINE_AVAILABLE, reason=_TEXT_PIPELINE_SKIP_REASON)
def test_processing_worker_routes_mixed_batch_to_correct_processors(
    qtbot, tmp_path, synthetic_text_photo, synthetic_diagram_photo
):
    """텍스트/도형이 섞인 배치를 넣으면 각 페이지가 올바른 처리기로 라우팅되고,
    PDF-1(입력 순서대로 병합)도 문서 유형과 무관하게 그대로 동작해야 한다."""
    text_path = tmp_path / "page1_text.png"
    diagram_path = tmp_path / "page2_diagram.png"
    cv2.imwrite(str(text_path), synthetic_text_photo.photo)
    cv2.imwrite(str(diagram_path), synthetic_diagram_photo.photo)
    work_dir = tmp_path / "work"

    worker = ProcessingWorker([text_path, diagram_path], work_dir)

    with qtbot.waitSignal(worker.finished, timeout=180000):
        worker.start()

    assert worker.merged_pdf_path is not None
    assert len(worker.page_results) == 2

    text_result, diagram_result = worker.page_results
    assert text_result.document_type == DocumentType.TEXT
    assert text_result.text is not None and text_result.text.strip() != ""
    assert diagram_result.document_type == DocumentType.DIAGRAM
    assert diagram_result.text is None
    assert diagram_result.sharpened_image is not None

    with pymupdf.open(worker.merged_pdf_path) as doc:
        assert doc.page_count == 2


def test_processing_worker_merges_successful_pages_when_one_page_misclassified_as_score(
    qtbot, tmp_path, monkeypatch, synthetic_diagram_photo
):
    """배치 중 한 페이지가 (분류 오탐으로) SCORE에 배정돼 처리에 실패해도, 나머지
    성공한 페이지들은 병합되어 저장 가능해야 한다(부분 실패를 배치 전체 실패와 분리).

    Phase2-1 분류 휴리스틱이 줄무늬 배경을 오선으로 오검출해 `SCORE`로 잘못 분류할
    가능성이 실제로 있으므로(docs/roadmap.md Phase2-1 참고), 여기서는 그 결과만
    `classify_document_type`을 몽키패치해 재현하고 나머지 파이프라인은 그대로 둔다.
    이 개발 머신엔 oemer 체크포인트가 없으므로 이 페이지는 `ScoreModelUnavailableError`로
    실패한다 — 어떤 예외로 실패하든 페이지 단위 실패 격리가 동작해야 한다는 점을
    검증하는 것이 이 테스트의 핵심이다.
    """
    image_path_1 = tmp_path / "page1_diagram.png"
    image_path_2 = tmp_path / "page2_misclassified.png"
    cv2.imwrite(str(image_path_1), synthetic_diagram_photo.photo)
    cv2.imwrite(str(image_path_2), synthetic_diagram_photo.photo)
    work_dir = tmp_path / "work"

    classifications = iter([DocumentType.DIAGRAM, DocumentType.SCORE])
    monkeypatch.setattr(
        "app.gui.worker.classify_document_type",
        lambda image, override=None: next(classifications),
    )

    worker = ProcessingWorker([image_path_1, image_path_2], work_dir)
    error_messages: list[str] = []
    worker.error_occurred.connect(error_messages.append)

    with qtbot.waitSignal(worker.finished, timeout=60000):
        worker.start()

    # 성공한 페이지(1장)만으로 병합 PDF가 만들어져 저장할 수 있어야 한다.
    assert worker.merged_pdf_path is not None
    assert worker.merged_pdf_path.exists()
    assert len(worker.page_results) == 1
    assert worker.page_results[0].input_path == image_path_1

    # 실패한 페이지는 조용히 사라지지 않고 기록되며, 요약 메시지로도 알려야 한다.
    assert len(worker.failed_pages) == 1
    assert worker.failed_pages[0][0] == image_path_2
    assert len(error_messages) == 1
    assert "1장" in error_messages[0]

    with pymupdf.open(worker.merged_pdf_path) as doc:
        assert doc.page_count == 1
    assert "oemer" in error_messages[0] or "체크포인트" in error_messages[0]


def test_processing_worker_fills_musicxml_path_for_score_page(
    qtbot, tmp_path, monkeypatch, synthetic_score_photo
):
    """Phase3-4: SCORE로 분류된 페이지가 성공하면 `PageResult.musicxml_path`가 채워져야
    한다(SCR-3 "MuseScore에서 열기" 버튼 활성화 조건). 이 개발 머신엔 oemer 체크포인트가
    없어 실제 OMR 추론은 할 수 없으므로, `app.processors.score.process_image`(라우터가
    호출하는 진입점) 자체를 몽키패치해 성공 경로만 검증한다.
    """
    from app.processors.score import ScoreResult

    image_path = tmp_path / "page1_score.png"
    cv2.imwrite(str(image_path), synthetic_score_photo.photo)
    work_dir = tmp_path / "work"

    monkeypatch.setattr(
        "app.gui.worker.classify_document_type",
        lambda image, override=None: DocumentType.SCORE,
    )

    def fake_score_process_image(image, output_pdf, **kwargs):
        musicxml_path = Path(output_pdf).with_suffix(".musicxml")
        musicxml_path.write_text("<score-partwise/>")
        # 이후 `assemble_pdf`가 pymupdf로 실제로 열어 병합하므로, 이어붙일 수 있는
        # 최소한의 유효한 1페이지 빈 PDF를 만든다(임의 바이트로는 병합 단계에서 깨진다).
        with pymupdf.open() as fake_pdf:
            fake_pdf.new_page()
            fake_pdf.save(str(output_pdf))
        return ScoreResult(musicxml_path=musicxml_path, pdf_path=Path(output_pdf))

    monkeypatch.setattr(
        "app.router.dispatch._PROCESSOR_REGISTRY",
        {DocumentType.SCORE: fake_score_process_image},
    )

    worker = ProcessingWorker([image_path], work_dir)
    with qtbot.waitSignal(worker.finished, timeout=60000):
        worker.start()

    assert worker.merged_pdf_path is not None
    assert len(worker.page_results) == 1
    page_result = worker.page_results[0]
    assert page_result.document_type == DocumentType.SCORE
    assert page_result.text is None
    assert page_result.musicxml_path is not None
    assert page_result.musicxml_path.exists()
