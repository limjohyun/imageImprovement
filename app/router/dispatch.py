"""RT-2: 분류 결과(`DocumentType`)에 따라 해당 `app.processors.*` 모듈로 위임한다.

텍스트(`app.processors.text.process_image`)와 도형(`app.processors.diagram.process_image`)
처리기가 등록되어 있다. 악보 처리기는 Phase3-1(`app/processors/score.py`)에서 구현된
뒤 `_PROCESSOR_REGISTRY`에 채워 넣으면 된다 — 지금은 그 확장 지점만 명확히 마련해둔다.
아직 구현되지 않은 유형으로 분류된 경우, 조용히 무시하거나 텍스트 처리기로 폴백하지 않고
`UnsupportedDocumentTypeError`를 명시적으로 던진다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np

from app.processors import diagram as diagram_processor
from app.processors import text as text_processor
from app.router.classifier import DocumentType, classify_document_type

logger = logging.getLogger(__name__)


class UnsupportedDocumentTypeError(NotImplementedError):
    """분류는 됐지만 아직 해당 문서 유형을 처리할 processors/* 모듈이 구현되지 않았을 때."""


ProcessorFn = Callable[..., Any]

# RT-2 확장 지점: Phase3-1이 `DocumentType.SCORE`를 app.processors.score의
# 진입점 함수로 채우면 된다.
_PROCESSOR_REGISTRY: dict[DocumentType, ProcessorFn] = {
    DocumentType.TEXT: text_processor.process_image,
    DocumentType.DIAGRAM: diagram_processor.process_image,
}


def route_and_process(
    image: np.ndarray,
    output_pdf: str | Path,
    *,
    override: DocumentType | None = None,
    **processor_kwargs: Any,
) -> Any:
    """RT-1 + RT-2: 이미지를 분류한 뒤 해당 처리기로 위임해 처리 결과를 반환한다.

    `override`가 주어지면 자동 분류를 건너뛰고 그 유형으로 바로 위임한다.
    `processor_kwargs`는 위임 대상 처리기의 진입점 함수(예: `process_image`)에
    그대로 전달된다(예: 텍스트 처리기의 `lang`, `dpi`).
    """
    document_type = classify_document_type(image, override=override)
    processor = _PROCESSOR_REGISTRY.get(document_type)
    if processor is None:
        raise UnsupportedDocumentTypeError(
            f"'{document_type.value}' 문서 유형을 처리할 processors/* 모듈이 아직 "
            "구현되지 않았습니다."
        )
    logger.info("문서 유형 '%s'(으)로 분류되어 해당 처리기에 위임합니다.", document_type.value)
    return processor(image, output_pdf, **processor_kwargs)
