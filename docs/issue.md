# 이슈 트래커 (진행 중 발견, 당장 처리하지 않은 항목)

각 Phase 진행 중 code-reviewer가 발견했지만 다음 Phase 진행에 즉시 필수적이지 않아
미룬 항목들. 우선순위가 낮은 정리/스타일 항목 위주. 해결하면 체크하고 커밋 링크를 남긴다.

## Phase1-2 (공통 전처리 파이프라인)

- [ ] **[스타일]** `tests/preprocess/test_ocr_improvement.py`가 `tests.fixtures.synthetic`의
  private 함수(`_photograph`, `_render_text_document`)를 직접 import해서 쓴다. 의도(기본
  fixture보다 가혹한 왜곡 강도를 커스터마이즈)는 정당하지만, 캡슐화 관례상 `synthetic.py`에
  파라미터를 받는 공개 헬퍼를 하나 추가해 정리하는 게 깔끔하다.
  (파일: `tests/preprocess/test_ocr_improvement.py`, `tests/fixtures/synthetic.py`)

## Phase1-3 (텍스트 OCR 처리기)

- [ ] **[문서 정합성]** `build_searchable_pdf`의 `MissingExternalToolError` 처리가 "Ghostscript
  없으면 명확히 드러난다"는 의도로 작성됐지만, 실제로는 `ocrmypdf.ocr()`의 기본
  `output_type='auto'`가 Ghostscript 부재 시 예외 없이 일반 PDF로 조용히 degrade된다(PDF/A
  변환만 건너뜀). 텍스트 레이어가 있는 PDF 자체는 정상 생성되므로 TXT-2 기능은 충족하지만,
  주석/독스트링의 "명확히 드러남" 주장과 실제 동작이 다르다. 필요하면 `output_type`을
  명시적으로 지정하거나 독스트링을 실제 동작에 맞게 수정.
  (파일: `app/processors/text.py`)
- [x] **[중복]** ~~`process_image()`가 `extract_text()`와 `build_searchable_pdf()`를 순서대로
  호출하는데, 두 함수 모두 내부에서 각각 `_require_tesseract()`를 실행해 약간의 중복이 있다~~
  → sidecar 통합 리팩터링(High #1 수정)으로 `process_image()`가 더 이상 `extract_text()`를
  재호출하지 않게 되어 자연히 해소됨.
  (파일: `app/processors/text.py`)
