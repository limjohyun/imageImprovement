"""pytest 공통 fixture.

Phase1-2(공통 전처리)부터 이후 모든 Phase의 테스트가 재사용하는 합성 촬영 사진
(텍스트/도형/악보) fixture를 여기서 노출한다. 실제 이미지 생성 로직은
`tests/fixtures/synthetic.py`에 있고, 여기서는 기본값을 적용한 얇은 pytest
fixture 래퍼만 둔다.
"""

from __future__ import annotations

import pytest

from tests.fixtures.synthetic import (
    ScoreRendererUnavailableError,
    SyntheticPhoto,
    make_diagram_photo,
    make_score_photo,
    make_text_photo,
)


@pytest.fixture
def synthetic_text_photo() -> SyntheticPhoto:
    """원근/조명/노이즈/저해상도 왜곡이 합성 적용된 텍스트 문서 촬영본."""
    return make_text_photo()


@pytest.fixture
def synthetic_diagram_photo() -> SyntheticPhoto:
    """원근/조명/노이즈/저해상도 왜곡이 합성 적용된 도형 문서 촬영본."""
    return make_diagram_photo()


@pytest.fixture
def synthetic_score_photo() -> SyntheticPhoto:
    """왜곡이 합성 적용된 악보 촬영본.

    MuseScore가 설치돼 있지 않으면(예: Phase3 착수 전) 렌더링할 수 없으므로,
    테스트를 실패시키는 대신 skip 처리한다.
    """
    try:
        return make_score_photo()
    except ScoreRendererUnavailableError as exc:
        pytest.skip(str(exc))
