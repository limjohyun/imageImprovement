# 이슈 트래커 (진행 중 발견, 당장 처리하지 않은 항목)

각 Phase 진행 중 code-reviewer가 발견했지만 다음 Phase 진행에 즉시 필수적이지 않아
미룬 항목들. 우선순위가 낮은 정리/스타일 항목 위주. 해결하면 체크하고 커밋 링크를 남긴다.

## Phase1-2 (공통 전처리 파이프라인)

- [ ] **[스타일]** `tests/preprocess/test_ocr_improvement.py`가 `tests.fixtures.synthetic`의
  private 함수(`_photograph`, `_render_text_document`)를 직접 import해서 쓴다. 의도(기본
  fixture보다 가혹한 왜곡 강도를 커스터마이즈)는 정당하지만, 캡슐화 관례상 `synthetic.py`에
  파라미터를 받는 공개 헬퍼를 하나 추가해 정리하는 게 깔끔하다.
  (파일: `tests/preprocess/test_ocr_improvement.py`, `tests/fixtures/synthetic.py`)
