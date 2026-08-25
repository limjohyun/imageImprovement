"""Phase1-5 수용 기준 검증: `MainWindow` 위젯 동작.

GUI-1(폴더/다중 파일 입력), 처리 파이프라인의 QThread 비블로킹 여부, GUI-4(저장)를
확인한다. GUI-2(미리보기)는 렌더링 헬퍼(`render_pdf_first_page_to_pixmap`)를 별도로
검증한다. 다이얼로그(`QFileDialog`)는 실제로 띄우지 않고 내부 메서드를 직접
호출하거나 `monkeypatch`로 대체해 headless(`QT_QPA_PLATFORM=offscreen`) 환경에서도
동작하게 한다.
"""

from __future__ import annotations

import shutil

import cv2
import pymupdf
import pytest

from app.gui.main_window import MainWindow, render_pdf_first_page_to_pixmap

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_GHOSTSCRIPT_AVAILABLE = shutil.which("gs") is not None
_QPDF_AVAILABLE = shutil.which("qpdf") is not None
_PIPELINE_AVAILABLE = _TESSERACT_AVAILABLE and _GHOSTSCRIPT_AVAILABLE and _QPDF_AVAILABLE

_PIPELINE_SKIP_REASON = "tesseract/ghostscript/qpdf 바이너리가 PATH에 없습니다."


def test_main_window_can_be_created(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "이미지 → PDF 변환"
    assert window.file_list_widget.count() == 0
    assert window.save_button.isEnabled() is False


def test_add_image_paths_populates_list_without_duplicates(qtbot, tmp_path):
    """GUI-1: 선택된 이미지가 목록에 쌓이고, 같은 파일을 다시 추가해도 중복되지 않는다."""
    window = MainWindow()
    qtbot.addWidget(window)

    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image-bytes")

    window._add_image_paths([image_path])
    window._add_image_paths([image_path])

    assert window.file_list_widget.count() == 1
    assert window._image_paths_in_list() == [image_path.resolve()]


def test_add_image_paths_uses_natural_sort_order(qtbot, tmp_path):
    """PDF-1(입력 순서대로 병합): 사전식 정렬(page1, page10, page2 ...)이 아니라
    파일명 안 숫자 크기를 기준으로 자연 정렬되어야 페이지 순서가 뒤섞이지 않는다."""
    window = MainWindow()
    qtbot.addWidget(window)

    names = ["page2.png", "page10.png", "page1.png"]
    paths = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"fake-image-bytes")
        paths.append(path)

    # 폴더 스캔은 사전식 정렬 결과를 넘길 수 있으므로, 이미 뒤섞인 순서로 들어와도
    # `_add_image_paths` 내부에서 자연 정렬되어야 한다.
    window._add_image_paths(sorted(paths))

    assert [p.name for p in window._image_paths_in_list()] == [
        "page1.png",
        "page2.png",
        "page10.png",
    ]


@pytest.mark.skipif(not _PIPELINE_AVAILABLE, reason=_PIPELINE_SKIP_REASON)
def test_start_processing_runs_in_background_and_enables_save(
    qtbot, tmp_path, synthetic_text_photo
):
    """처리 시작 직후에도 UI 제어권이 즉시 돌아오고(QThread), 완료 후 저장 버튼이 켜져야 한다."""
    image_path = tmp_path / "page1.png"
    cv2.imwrite(str(image_path), synthetic_text_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)
    window._add_image_paths([image_path])

    with qtbot.waitSignal(window.processing_completed, timeout=120000):
        window._start_processing()
        # 처리 시작 직후 스레드가 끝나길 기다리지 않고 곧바로 이 지점에 도달해야 한다.
        assert window.process_button.isEnabled() is False

    assert window.save_button.isEnabled() is True
    assert window._merged_pdf_path is not None
    assert window._merged_pdf_path.exists()
    with pymupdf.open(window._merged_pdf_path) as doc:
        assert doc.page_count == 1


@pytest.mark.skipif(not _PIPELINE_AVAILABLE, reason=_PIPELINE_SKIP_REASON)
def test_save_result_writes_pdf_to_chosen_path(qtbot, tmp_path, monkeypatch, synthetic_text_photo):
    """GUI-4: 저장 버튼을 누르면 사용자가 지정한 경로에 최종 PDF가 실제로 생성된다."""
    image_path = tmp_path / "page1.png"
    cv2.imwrite(str(image_path), synthetic_text_photo.photo)

    window = MainWindow()
    qtbot.addWidget(window)
    window._add_image_paths([image_path])

    with qtbot.waitSignal(window.processing_completed, timeout=120000):
        window._start_processing()

    destination = tmp_path / "final_output.pdf"
    monkeypatch.setattr(
        "app.gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(destination), "PDF 파일 (*.pdf)"),
    )

    window._on_save_clicked()

    assert destination.exists()
    with pymupdf.open(destination) as doc:
        assert doc.page_count == 1


def test_render_pdf_first_page_to_pixmap_returns_non_null_pixmap(qtbot, tmp_path):
    """GUI-2 미리보기 렌더링 헬퍼가 PDF 첫 페이지를 유효한 QPixmap으로 변환해야 한다."""
    pdf_path = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 40), "테스트 페이지")
    doc.save(pdf_path)
    doc.close()

    pixmap = render_pdf_first_page_to_pixmap(pdf_path)

    assert not pixmap.isNull()
    assert pixmap.width() > 0
    assert pixmap.height() > 0
