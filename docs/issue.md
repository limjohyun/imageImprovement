# 이슈 트래커 (진행 중 발견, 당장 처리하지 않은 항목)

각 Phase 진행 중 code-reviewer가 발견했지만 다음 Phase 진행에 즉시 필수적이지 않아
미룬 항목들. 우선순위가 낮은 정리/스타일 항목 위주. 해결하면 체크하고 커밋 링크를 남긴다.

## Phase1-2 (공통 전처리 파이프라인)

- [x] **[스타일]** ~~`tests/preprocess/test_ocr_improvement.py`가 `tests.fixtures.synthetic`의
  private 함수(`_photograph`, `_render_text_document`)를 직접 import해서 쓴다.~~
  → `synthetic.py`의 `make_text_photo()`에 `max_jitter_ratio`/`noise_sigma`/`downsample_scale`
  키워드 인자를 추가해 왜곡 강도를 공개적으로 노출했고(기본값은 기존과 동일, 하위 호환),
  테스트 파일이 private 함수 대신 이 public 헬퍼를 쓰도록 변경해 해소됨.
  (파일: `tests/preprocess/test_ocr_improvement.py`, `tests/fixtures/synthetic.py`)

## Phase1-3 (텍스트 OCR 처리기)

- [x] **[문서 정합성]** ~~`build_searchable_pdf`의 `MissingExternalToolError` 처리가 "Ghostscript
  없으면 명확히 드러난다"는 의도로 작성됐지만, 실제로는 예외 없이 일반 PDF로 조용히
  degrade된다.~~
  → 실제 동작(Ghostscript 부재 시 `output_type='auto'`가 예외 없이 PDF/A 변환만 건너뛰고
  조용히 일반 PDF로 degrade됨, 텍스트 레이어는 정상 생성되어 TXT-2는 충족)을 code-reviewer가
  직접 재현 검증했고, `MissingExternalToolError` docstring을 그 실제 동작에 맞게 수정해
  해소됨. 코드 동작 자체는 변경하지 않음(새 하드 디펜던시를 만들지 않기 위한 의도적 선택).
  (파일: `app/processors/text.py`)
- [x] **[중복]** ~~`process_image()`가 `extract_text()`와 `build_searchable_pdf()`를 순서대로
  호출하는데, 두 함수 모두 내부에서 각각 `_require_tesseract()`를 실행해 약간의 중복이 있다~~
  → sidecar 통합 리팩터링(High #1 수정)으로 `process_image()`가 더 이상 `extract_text()`를
  재호출하지 않게 되어 자연히 해소됨.
  (파일: `app/processors/text.py`)

## Phase1-4 (PDF 조립 최소 구현)

- [x] **[사소]** ~~`assemble_pdf`에서 `output_pdf.parent.mkdir(...)`이 각 입력 PDF의 페이지 수
  검증(루프 안쪽)보다 먼저 실행돼, 루프 중간에 `ValueError`(0페이지 PDF 등)가 나도 출력
  디렉터리는 이미 생성된 채로 남는다.~~
  → `mkdir` 호출을 페이지 병합/검증이 모두 끝난 뒤 `merged.save()` 직전으로 이동해 해소됨.
  회귀 테스트 `test_assemble_pdf_does_not_create_output_dir_on_validation_failure` 추가.
  (파일: `app/pdf_assembly/assemble.py`, `tests/pdf_assembly/test_assemble.py`)
- [x] **[사소]** ~~존재하지 않는 경로와 "파일이 아닌 경로"(디렉터리 등)가 `path.is_file()`
  검사 하나로 뭉뚱그려져 동일한 `FileNotFoundError` 메시지를 받는다.~~
  → `path.exists()` → `path.is_file()` 순차 검사로 분리해 미존재/디렉터리 케이스에 서로 다른
  에러 메시지를 내도록 수정. 회귀 테스트 `test_assemble_pdf_rejects_directory_path` 추가.
  (파일: `app/pdf_assembly/assemble.py`, `tests/pdf_assembly/test_assemble.py`)
