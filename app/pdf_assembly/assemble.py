"""PDF-1: 여러 장의 단일 페이지 PDF를 순서대로 하나의 PDF로 합친다.

`app.processors.text.process_image`(및 이후 Phase2/3의 도형/악보 processor)는
페이지 한 장당 PDF 한 개를 만든다. 이 모듈은 그렇게 만들어진 PDF 경로 목록을
호출자가 정한 순서 그대로 병합하기만 한다 — 개별 페이지의 OCR/벡터화/재조판은
이미 끝난 상태라고 가정하며, 재정렬/삭제(PDF-2)는 Phase4 GUI의 몫이라 다루지
않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)


def assemble_pdf(page_pdf_paths: Sequence[str | Path], output_pdf: str | Path) -> Path:
    """PDF-1: 단일 페이지 PDF 경로들을 주어진 순서대로 하나의 PDF로 병합한다.

    각 입력 PDF는 존재하고 페이지가 1개 이상이어야 한다 — 잘못된 입력을 조용히
    건너뛰면 최종 PDF에서 페이지가 소리 없이 빠지는 문제로 이어지므로, 여기서
    명확한 예외로 드러낸다.
    """
    if len(page_pdf_paths) == 0:
        raise ValueError("병합할 PDF 경로가 비어 있습니다.")

    resolved_paths = [Path(p) for p in page_pdf_paths]
    for path in resolved_paths:
        if not path.is_file():
            raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {path}")

    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    merged = pymupdf.open()
    try:
        for path in resolved_paths:
            with pymupdf.open(path) as page_doc:
                if page_doc.page_count == 0:
                    raise ValueError(f"페이지가 없는 PDF입니다: {path}")
                merged.insert_pdf(page_doc)
        merged.save(output_pdf)
    finally:
        merged.close()

    logger.info("PDF %d개를 %s(으)로 병합했습니다.", len(resolved_paths), output_pdf)
    return output_pdf
