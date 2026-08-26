# roadmap.md — 스마트폰 촬영 이미지 → 고화질 PDF Tool

`prd.md`를 Shrimp Task Manager로 분해한 결과. 총 26개 task. Phase1은 선형 체인이고, Phase2(도형)와 Phase3(악보)는 둘 다 Phase2-1(router)에만 의존하므로 서로 병렬로 진행 가능하다 — Phase4는 이 두 갈래가 모두 끝나야 시작할 수 있도록 Phase2-5와 Phase3-5 양쪽을 전제 조건으로 건다(최초 생성 시 Phase3-5만 걸려 있던 누락을 검토 후 수정함). Shrimp 원본 데이터는 `shrimp_data/tasks.json`에 있으며, 이 문서는 사람이 읽기 좋은 요약본이다. **주의**: Shrimp에서 task 상태가 바뀌어도(진행중/완료 등) 이 파일은 자동 갱신되지 않는 스냅샷이다 — 최신 상태는 `list_tasks`로 확인할 것.

각 task ID는 Shrimp Task Manager의 실제 task ID이며, `execute_task <ID>`로 실행하거나 `get_task_detail <ID>`로 상세(구현 가이드 pseudocode 포함)를 조회할 수 있다.

## Phase 1 — 공통 전처리 + 텍스트 OCR + 최소 GUI (최우선)

가장 검증된 경로(OpenCV+OCRmyPDF)로 end-to-end 파이프라인을 먼저 완성. 이후 모든 Phase의 전제 조건.

| # | Task | 요구사항 ID | 의존 | ID | 상태 |
|---|---|---|---|---|---|
| 1 | 프로젝트 스캐폴딩 (git init, venv, 폴더구조, pytest) | — | 없음 | `954d8b88` | ✅ 완료 |
| 1b | 합성 테스트 픽스처 생성 유틸리티 (텍스트/도형/악보 왜곡 이미지 코드로 생성) | — | #1 | `ef4c4c61` | ✅ 완료 |
| 2 | 공통 전처리 파이프라인 (원근보정/deskew/조명보정/업스케일) | PRE-1~5 | #1, #1b | `00a177ec` | ✅ 완료 |
| 3 | 텍스트 OCR 처리기 (OCR + OCRmyPDF) | TXT-1,2 | #2 | `3770f54b` | ✅ 완료 |
| 4 | PDF 조립 최소 구현 (단순 병합) | PDF-1 | #3 | `c48f1148` | ✅ 완료 |
| 5 | 최소 GUI (입력/미리보기/저장, 처리 파이프라인은 QThread로 실행해 UI 비블로킹 보장) | GUI-1,2,4 | #4 | `bce4fa7d` | ✅ 완료 |
| 6 | 텍스트 검수 UI | TXT-3 | #5 | `40e5540c` | ✅ 완료 |
| 7 | Phase1 End-to-End 검증 | §9 Phase1 | #6 | `185b6d07` | ✅ 완료 |

`#1b`은 Phase1-2보다 먼저 실행되고 이후 모든 task가 선형/분기 체인으로 그 뒤를 잇기 때문에, 표에 나온 다른 task들이 fixture를 명시적으로 다시 의존성에 걸지 않아도 이미 사용 가능한 상태로 실행된다(전이적 의존).

## Phase 2 — 도형/그래프 처리 + 유형 라우팅 도입

| # | Task | 요구사항 ID | 의존 | ID | 상태 |
|---|---|---|---|---|---|
| 1 | 문서 유형 라우팅(router) 구현 | RT-1,2 | Phase1#7 | `7ef7d4ad` | ✅ 완료 |
| 2 | 도형 선명화 | DIA-1 | #1 | `150b2fa8` | ✅ 완료 |
| 3 | 도형 벡터화 옵션 + 한계 고지 | DIA-2,3 | #2 | `5b71299b` | ✅ 완료 |
| 4 | GUI에 도형 처리 경로 연결 | DIA-3(UI) | #3 | `0d043c72` | ✅ 완료 |
| 5 | Phase2 End-to-End 검증 | §9 Phase2/3 | #4 | `d2d67738` | ✅ 완료 |

## Phase 3 — 악보 처리 (OMR)

| # | Task | 요구사항 ID | 의존 | ID | 상태 |
|---|---|---|---|---|---|
| 1 | 악보 OMR 인식 (oemer 연동) | SCR-1 | Phase2#1 | `cfb53ee4` | ✅ 완료 |
| 2 | 재조판 PDF 생성 (MuseScore 연동) — ⚠️사전 설치: MuseScore 4 | SCR-2 | #1 | `b8cba231` | ✅ 완료 |
| 3 | 악보 오류 검수 경로 (외부 편집기 열기, 동일하게 MuseScore 설치 필요) | SCR-3 | #2 | `59367417` | ⬜ 대기 |
| 4 | GUI에 악보 처리 경로 연결 | — | #3 | `0deef3cf` | ⬜ 대기 |
| 5 | Phase3 End-to-End 검증 | §9 Phase2/3 | #4 | `96bc862b` | ⬜ 대기 |

## Phase 4 — GUI 고도화

| # | Task | 요구사항 ID | 의존 | ID | 상태 |
|---|---|---|---|---|---|
| 1 | 수동 보정 (자르기/회전) | GUI-3(일부) | Phase2#5, Phase3#5 | `851d5923` | ⬜ 대기 |
| 2 | 도형/악보 검수 위젯 통합 | GUI-3(전체) | #1 | `32dc96c8` | ⬜ 대기 |
| 3 | 페이지 재정렬/삭제 | PDF-2 | #2 | `6a46cdf1` | ⬜ 대기 |
| 4 | 유형 자동 라우팅 정교화 | RT-1,2(고도화) | #3 | `9d32a092` | ⬜ 대기 |
| 5 | Phase4 End-to-End 검증 (혼합 워크플로우) | §9 Phase4 | #4 | `1abca8b7` | ⬜ 대기 |

## Phase 5 — 선택적 클라우드 백업 (낮은 우선순위)

핵심 파이프라인 완성 후 진행하는 부가 기능. 오프라인 목표(§2)와 상충하지 않도록 opt-in.

| # | Task | 요구사항 ID | 의존 | ID | 상태 |
|---|---|---|---|---|---|
| 1 | 로컬 저장 우선 보장 + 백업 설정 UI(기본 off) | BKP-1 | Phase4#5 | `90830178` | ⬜ 대기 |
| 2 | Supabase 업로드 구현 | BKP-2 | #1, #3 | `005aed8e` | ⬜ 대기 |
| 3 | 자격증명 관리 (.env) | BKP-4 | #1 | `84f668f8` | ⬜ 대기 |
| 4 | Phase5 End-to-End 검증 (오프라인 보장 포함) | BKP-3, §9 Phase5 | #2, #3 | `ab376901` | ⬜ 대기 |

## 요구사항 ID 커버리지 체크

prd.md의 모든 요구사항 ID가 어느 task에 매핑되는지 확인:

- PRE-1~5: Phase1#2 ✅
- RT-1,2: Phase2#1 (도입) + Phase4#4 (고도화) ✅
- TXT-1~3: Phase1#3, #6 ✅
- DIA-1~3: Phase2#2,#3,#4 ✅
- SCR-1~3: Phase3#1,#2,#3 ✅
- PDF-1,2: Phase1#4, Phase4#3 ✅
- GUI-1~4: Phase1#5,#6 + Phase4#1,#2 ✅
- BKP-1~4: Phase5 전체 ✅

## ultrathink 검토 메모

roadmap.md 생성 직후 의존성 그래프와 각 task 내용을 다시 훑어보며 발견한 사항. 전부 해결 완료.

**1차 검토에서 발견해 즉시 수정:**
- Phase4-1이 원래 Phase3#5에만 의존해 있었음 → Phase2#4(도형 GUI 연결)/#5(E2E)가 끝나지 않아도 Phase4에 진입할 수 있는 구멍이 있었음. Phase4-2(도형/악보 검수 위젯 통합)는 Phase2 산출물이 실제로 필요하므로 Phase2#5도 전제 조건으로 추가.
- Phase5-2(Supabase 업로드)의 pseudocode가 Phase5-3(자격증명 로더)의 함수를 호출하는데도 의존성에 Phase5-3이 빠져 있었음(원래 pseudocode 주석도 "Phase5-4"로 잘못 표기돼 있었음) → 의존성과 주석 모두 수정.

**2차 검토(사용자 판단 반영)에서 해결:**
- **테스트 픽스처 부재** → 사용자가 "합성 왜곡 이미지 생성" 방식을 선택. `Fixtures-1`(`ef4c4c61`) task를 Phase1-1 다음에 추가하고 Phase1-2의 의존성에 연결(전이적으로 이후 모든 task가 사용 가능). 텍스트/도형은 PIL/OpenCV로 직접 렌더링 후 원근왜곡+노이즈+다운샘플을 합성 적용하고, 악보는 손으로 그린 도형이 아니라 music21로 작성한 MusicXML을 실제 엔그레이빙 렌더러로 그려야 oemer 같은 사전학습 모델이 인식할 수 있다는 점을 task notes에 명시.
- **GUI 스레딩** → pytest-qt 공식 문서([waitSignal 패턴](https://pytest-qt.readthedocs.io/en/latest/signals.html))에 QThread 완료 신호를 기다리는 표준 검증 패턴이 이미 존재함을 확인. 별도 issue.md로 미루지 않고 Phase1-5(`bce4fa7d`)의 implementationGuide에 QThread 기반 ProcessingWorker 설계를, verificationCriteria에 `qtbot.waitSignal(worker.finished, ...)` 기반 비동기 검증을 직접 반영.
- **외부 바이너리 선행 설치 시점** → Phase1-3(Tesseract/Ghostscript/qpdf)과 Phase3-2·3-3(MuseScore)로 특정해 각 task의 notes에 "사전 설치 필요"를 명시하고, 위 표에도 ⚠️ 표시로 반영.

**여전히 참고만 하면 되는 것 (조치 불필요):**
- **Task 크기**: Phase1-2(전처리 4종 통합)와 Phase1-5(최소 GUI)는 Shrimp의 "1~2일 내 완료" 가이드라인 대비 다소 큼 — 개인 프로젝트 특성상 의도적으로 모듈 단위로 묶었으나, 실제 진행하다 막히면 그때 세분화해도 무방.

## 진행 상황

**저장소**: https://github.com/limjohyun/imageImprovement (main 브랜치, Phase1-1 커밋까지 push 완료)

### 환경 준비 (Phase1-1 착수 전)

Phase1에 필요한 라이브러리/프로그램을 먼저 설치함. 실제로 설치해보며 발견한 것들을 Phase1-1/Phase1-3 task notes에 반영해둠(위 링크의 `get_task_detail`로 상세 확인 가능):

- venv는 **Python 3.12**로 생성(3.13은 PEP 667 때문에 basicsr 설치 자체가 깨짐 — 실제 재현 확인함). pyproject.toml의 Python 버전 제약을 `>=3.12,<3.13`으로 명시함.
- basicsr는 설치되어도 import 시점에 `torchvision.transforms.functional_tensor`(최신 torchvision에서 삭제됨) 오류가 남아 있어 한 줄 패치가 필요함 — `scripts/patch_basicsr.py`로 재현 가능하게 만들어 커밋함(venv 재생성 시 이 스크립트를 다시 실행).
- pip 패키지(opencv-python, numpy, Pillow, pymupdf, img2pdf, reportlab, pyside6, pytest, pytest-qt, ruff, pytesseract, ocrmypdf, torch-cpu, realesrgan, basicsr) 전부 설치 및 import 확인 완료.
- 외부 프로그램: Tesseract 5.5.3·qpdf 12.3.2 설치 및 PATH 등록 완료. **Ghostscript는 winget 카탈로그에 없어 미설치 — Phase1-3 착수 직전에 수동 설치하기로 함(사용자 결정, 아직 유효).**

### ✅ Phase1-1: 프로젝트 스캐폴딩 — 완료

- `python-dev-expert`가 구현(git init, pyproject.toml, app/ 6개 서브패키지, tests/, .gitignore, README, `scripts/patch_basicsr.py`).
- `code-reviewer`가 커밋 전 검토해서 실제로 재현 가능한 버그 2건(HIGH)을 찾음: pyproject.toml에 `[build-system]`이 없어 `pip install -e .`가 `shrimp_data/`를 최상위 패키지로 오인해 실패하던 문제, README에 재현 가능한 설치 절차(특히 torch CPU 전용 인덱스)가 없던 문제. 버전 상한이 없다는 MEDIUM 지적도 있었음.
- `python-dev-expert`가 세 가지(build-system 추가, README 설치 절차 보강, 의존성 버전 `==` 고정) 모두 수정하고 재검증(`pip install -e ".[dev]"`, `pytest --collect-only`, `ruff check .` 전부 통과) 완료.
- 문서를 `docs/`로 재구성(`prd.md`, `roadmap.md` → `docs/`)하고 `README.md`·`.claude/agents/*.md`의 참조 경로 갱신.
- `git commit` + `git push`로 GitHub(`origin/main`)에 반영 완료.
- 남겨둔 참고사항(조치 안 함): `.mcp.json`에 다른 워크스페이스(`invoice-web`)의 절대경로가 하드코딩된 채 커밋됨 — 비밀정보는 아니지만 다른 컴퓨터에서 클론하면 Shrimp 연결이 깨짐.

### ✅ Phase1-1b: 합성 테스트 픽스처 생성 유틸리티 — 완료

- **환경 전환**: 이 태스크부터 개발 환경을 Windows에서 **macOS**로 전환함(사용자 결정 — 아이폰으로 촬영한 사진을 다루므로 macOS에서 계속 진행). Homebrew 설치 → `python@3.12`/`tesseract`/`ghostscript`/`qpdf` 설치 → `.venv` 재생성 → `pip install -e ".[dev]"` → `scripts/patch_basicsr.py` 전부 재검증 완료(`pytest`/`ruff` 통과). `CLAUDE.md`/`README.md`/`docs/prd.md`의 Windows 전용 안내(PowerShell 명령, "(Windows)" 표기 등)를 macOS 기준으로 갱신함. Ghostscript는 Windows에서는 winget에 없어 미설치였으나, macOS에서는 Homebrew로 정상 설치됨(Phase1-3의 ⚠️ 표시는 이제 해소된 상태).
- Shrimp Task Manager MCP는 `npx -y mcp-shrimp-task-manager` 방식으로 이 macOS 머신에 새로 연결함(로컬 clone/build 불필요). 다만 이전 Windows 머신의 `shrimp_data/`(git-ignore 대상)는 옮겨오지 않아 태스크 그래프가 비어 있음 — 사용자 결정에 따라 Shrimp에 태스크를 재구성하지 않고 이 `docs/roadmap.md` 스냅샷을 기준으로 계속 진행하기로 함.
- `python-dev-expert`가 구현: `tests/fixtures/synthetic.py`(텍스트/도형은 PIL/OpenCV로 렌더링 후 원근왜곡+조명그라디언트+가우시안노이즈+다운샘플 합성, 악보는 music21로 MusicXML 작성 후 MuseScore CLI로 엔그레이빙 PNG 렌더링), `tests/fixtures/test_synthetic.py`(스모크 테스트), `tests/conftest.py`(pytest fixture로 wrapping). `pyproject.toml` dev 의존성에 `music21==10.5.0` 추가.
- 악보 fixture는 MuseScore가 없으면(`find_musescore_executable()`이 `None` 반환) `ScoreRendererUnavailableError` → `pytest.skip`으로 우아하게 건너뛰도록 설계함. 이 머신에는 아직 MuseScore가 설치돼 있지 않아(Phase3 착수 전까지 의도적으로 보류) 현재 이 fixture는 skip 상태.
- `code-reviewer`가 검토: HIGH/MEDIUM 이슈 없음. LOW 3건 중 "MuseScore 없이 skip되는 경로라 music21 MusicXML 생성 로직 자체가 pytest에서 exercise 안 됨" 1건을 반영해 `_build_synthetic_score()` 단독 스모크 테스트(`test_build_synthetic_score_produces_well_formed_musicxml`)를 추가함. 나머지 2건(왜곡 판정 테스트의 약한 assertion, macOS 마이그레이션 문서 변경과 커밋 분리 필요)은 blocking 아님으로 판단해 참고만 하고 넘어감.
- 최종 검증: `./.venv/bin/python -m pytest -q` → 7 passed, 1 skipped(MuseScore 미설치, 의도된 결과). `./.venv/bin/python -m ruff check .` → 통과.

### ✅ Phase1-3: 텍스트 OCR 처리기 — 완료

- Homebrew `tesseract`/`ghostscript`/`qpdf` 설치 확인 완료. 한국어 인식(TXT-1)을 위해 `tessdata_fast` 저장소의 `kor.traineddata`(약 1.6MB)를 `/opt/homebrew/share/tessdata/`에 받아 추가함(전체 언어팩(`tesseract-lang`, 수백MB) 대신 필요한 언어만 최소로 설치 — 사용자 결정).
- `python-dev-expert`가 `app/processors/text.py` 구현: `extract_text`(TXT-1, pytesseract), `build_searchable_pdf`(TXT-2, img2pdf+OCRmyPDF), `process_image`/`process_image_file`(진입점). `app.preprocess.run_pipeline`을 그대로 재사용.
- `code-reviewer`가 검토해 HIGH 1건 발견: `extract_text()`와 `build_searchable_pdf()`가 Tesseract를 각각 별도로 실행해 검수용 텍스트와 실제 PDF 텍스트 레이어가 미묘하게 달라지는 문제(재현 확인됨) — `ocrmypdf.ocr(..., sidecar=...)`로 한 번의 실행으로 통합해 해결. MEDIUM 1건: 한글 인식이 테스트에서 전혀 검증되지 않던 문제 — 사용자 확인 후 macOS 시스템 한글 폰트로 렌더링하는 fixture(`make_korean_text_photo`)를 추가해 실측 유사도 0.98 확인. LOW(유사도 임계값 완화, logger 미사용)도 함께 수정. 나머지 사소한 지적(Ghostscript degrade 시 문서 정합성)은 `docs/issue.md`에 기록.
- 최종 검증: `pytest -q` → 48 passed, 2 skipped(MuseScore 미설치, 의도된 결과). `ruff check .` → 통과.

### ✅ Phase1-5: 최소 GUI — 완료

- `python-dev-expert`가 구현: `app/gui/worker.py`(`ProcessingWorker`, `QThread` 상속 — 텍스트 파이프라인(전처리+OCR+PDF 병합)을 별도 스레드에서 실행하고 진행률/페이지 결과/에러를 시그널로 전달, 커스텀 `finished`를 두지 않고 QThread 내장 시그널을 그대로 사용해 `qtbot.waitSignal(worker.finished, ...)` 패턴과 충돌 없게 함), `app/gui/main_window.py`(`MainWindow` — 폴더/파일 선택(GUI-1), 원본/처리 결과 나란히 미리보기(GUI-2, `pymupdf`로 PDF 첫 페이지 렌더링), PDF로 저장(GUI-4)), `app/gui/__init__.py`/`__main__.py`(`python -m app.gui` 진입점).
- `code-reviewer`가 검토해 HIGH 1건 발견: 폴더 스캔이 사전식 정렬(`page1, page10, page11, page2` 순)이라 PDF-1(입력 순서대로 병합) 요구사항이 조용히 깨질 수 있던 문제 — 자연 정렬(natural sort) 키를 도입해 `_add_image_paths`가 추가할 때마다 전체 목록을 재정렬하도록 수정하고 회귀 테스트 추가. MEDIUM 3건도 함께 수정: macOS AppleDouble(`._*`) 사이드카 파일이 폴더 스캔 필터를 통과해 배치 처리가 조용히 중단되던 문제(점(`.`)으로 시작하는 파일 제외), `closeEvent` 확인 문구가 "중단"이라고 안내하면서 실제로는 처리가 끝날 때까지 기다리던 문구/동작 불일치(문구를 실제 동작에 맞게 수정), 앱 종료 시 임시 작업 디렉터리(처리된 페이지 PDF 포함)가 정리되지 않아 PACS 스캔 등 민감 문서 사본이 시스템 temp에 남던 문제(`closeEvent`에 정리 로직 추가). LOW 2건(HEIC 미지원, `lang` 파라미터 미노출)은 Phase1 범위 밖/블로킹 아님으로 판단해 보류.
- 최종 검증: `pytest -q` → 63 passed, 2 skipped(MuseScore 미설치, 의도된 결과). `ruff check .` → 통과.

### ✅ Phase1-6: 텍스트 검수 UI — 완료

- `python-dev-expert`가 구현: `MainWindow`에 텍스트 검수 패널(`text_review_edit`, `QPlainTextEdit`) 추가. 페이지 선택 시 `_refresh_text_review`가 해당 `PageResult.text`를 채우고(미처리 페이지는 비활성화), 사용자가 편집하면 `_on_review_text_changed`가 `textChanged` 시그널로 즉시 `PageResult.text`(mutable dataclass)에 반영. PDF 텍스트 레이어 재생성(OCRmyPDF 재실행)은 의도적으로 범위 밖으로 남김(TXT-3 수용 기준은 "확인/수정"이지 "PDF 재반영"이 아님).
- `qa-test-engineer`가 `tests/gui/test_main_window.py`에 테스트 6개 추가(미선택/미처리 시 비활성화, 처리 후 텍스트 채움, 편집 즉시 반영과 페이지 전환 후 유실 없음 확인, 재처리 시 패널 초기화, 실제 파이프라인으로 OCR 텍스트 채움 검증).
- `code-reviewer`가 검토해 MEDIUM 1건 발견: 검수 중인 텍스트 수정 내용은 메모리에만 있는데(파일로 저장되지 않음) 재처리("처리 시작" 재클릭) 시 경고 없이 사라지던 문제 — `_results_by_input`가 비어있지 않을 때 확인 대화상자를 추가해 해결. LOW 2건도 함께 수정: `blockSignals(True)/(False)` 수동 쌍이 예외 시 위젯을 영구히 신호 차단 상태로 남길 수 있던 문제(`QSignalBlocker` 컨텍스트 매니저로 교체), 재처리 시 초기화 문구가 실제 선택 상태와 안 맞던 문제(`_reset_text_review_panel`이 현재 선택된 페이지가 있으면 `_refresh_text_review`로 위임해 정확한 문구를 재사용하도록 정리).
- 최종 검증: `pytest -q` → 68 passed, 2 skipped(MuseScore 미설치·Real-ESRGAN 가중치 미지정, 기존과 동일한 의도된 결과). `ruff check .` → 통과.

### ✅ Phase1-7: Phase1 End-to-End 검증 — 완료 (Phase1 전체 완료)

- `qa-test-engineer`가 `tests/gui/test_e2e_phase1.py`에 §9 Phase1 수용 기준("왜곡·저해상도 샘플 이미지 1장을 입력해 검색 가능한 PDF가 생성되는지")을 검증하는 end-to-end 테스트를 작성. `synthetic_text_photo`(원근왜곡+조명그라디언트+카메라노이즈+다운샘플 합성)를 입력으로 실제 `MainWindow`를 통해 입력(GUI-1)→백그라운드 처리(QThread)→미리보기(GUI-2)→텍스트 검수(TXT-3)→저장(GUI-4)까지 한 흐름으로 잇고, 저장된 PDF를 다시 열어 텍스트 레이어가 원문과 유사도 0.7 이상이며 특정 단어가 실제로 검색됨을 확인(TXT-2 "검색 가능한 PDF" 실증).
- 별도로 발견된 코드 결함 없음 — 테스트가 첫 실행에 통과.
- 최종 검증: `pytest -q` → 69 passed, 2 skipped(MuseScore 미설치·Real-ESRGAN 가중치 미지정, 기존과 동일한 의도된 결과). `ruff check .` → 통과.
- **Phase1(공통 전처리 + 텍스트 OCR + 최소 GUI) 전체 완료.** 다음은 Phase2(도형/그래프 처리 + 유형 라우팅) 착수.

### ✅ Phase2-1: 문서 유형 라우팅(router) 구현 — 완료

- `python-dev-expert`가 구현: `app/router/classifier.py`(`DocumentType` enum, `classify_document_type(image, *, override=None)` — 오선 검출→도형 컨투어 판정→기본값 TEXT 순서의 결정론적 OpenCV 휴리스틱 3분류, `override` 지정 시 휴리스틱 완전 우회), `app/router/dispatch.py`(`route_and_process` — 분류 결과를 `_PROCESSOR_REGISTRY` dict로 위임, TEXT만 `app.processors.text.process_image`에 실제 연결, DIAGRAM/SCORE는 아직 레지스트리에 없어 `UnsupportedDocumentTypeError`를 명시적으로 던짐), `app/router/__init__.py`(재노출), `tests/router/*`(분류/오버라이드/디스패치 테스트). Phase2-2(도형 처리기)/Phase3-1(악보 처리기)이 생기면 `_PROCESSOR_REGISTRY`에 항목만 추가하면 되는 확장 지점으로 설계.
- `code-reviewer`가 검토: 크래시/보안/요구사항 위반(HIGH)은 없음. MEDIUM 3건은 휴리스틱 오탐 시나리오(표가 있는 문서→DIAGRAM 오분류, 줄무늬 배경→SCORE 오분류, 텍스트 라벨 없는 단일 대형 도형→TEXT 오분류) — RT-1이 요구하는 수동 오버라이드로 구제 가능하고, 자동 분류 정교화는 로드맵상 Phase4-4("유형 자동 라우팅 정교화")에서 다루기로 이미 계획돼 있어 지금 추가 튜닝하지 않고 알려진 한계로 남기기로 판단(과설계 방지). LOW 1건(빈 이미지/비-uint8 입력 시 원인 불명의 OpenCV 예외 노출)은 공개 API 경계 방어 코드로 저비용 수정 가치가 있어 반영: `_binarize_for_analysis`에 빈 이미지·비-uint8 dtype에 대한 명시적 `ValueError` 가드 추가 및 회귀 테스트 2건 추가.
- 최종 검증: `pytest -q` → 80 passed, 2 skipped(MuseScore 미설치·Real-ESRGAN 가중치 미지정, 기존과 동일한 의도된 결과). `ruff check .` → 통과.

### ✅ Phase2-2: 도형 선명화 — 완료

- `python-dev-expert`가 구현: `app/processors/diagram.py`(`sharpen_diagram` — 양방향 필터로 업스케일 잔노이즈를 먼저 정리한 뒤 언샤프 마스킹으로 윤곽 강조, `build_diagram_pdf` — `img2pdf`로 텍스트 레이어 없이 이미지를 그대로 PDF 한 장으로 감쌈, `process_image`/`process_image_file` — `text.py`와 동일한 스타일의 진입점). Real-ESRGAN/고전 업스케일(해상도 확대 자체)은 공통 전처리 단계에서 이미 처리되므로 재구현하지 않고 "선명화"에만 집중. `_PROCESSOR_REGISTRY` 호출 규약과 호환되는 시그니처로 만들되 라우터 등록 자체는 Phase2-4로 미룸. `tests/processors/test_diagram.py`(라플라시안 분산 개선, 빈 이미지 예외, PDF 유효성/텍스트 레이어 없음 검증).
- `code-reviewer`가 검토: 차단급 문제 없음. 색공간/dtype/in-place 오염/이중 업스케일 모두 문제 없음 확인, DIA-2·DIA-3·라우터 등록을 범위에서 뺀 것도 의도된 경계로 판단, 형태학적 선 굵기 보정을 도입하지 않은 판단(반전 정보 없이 적용 시 얇은 선 삭제·인접 도형 병합 위험)도 타당하다고 확인. 경미한 지적 3건 중 미사용 `logger` 변수(죽은 코드)만 제거해 반영. 기본 샤프닝 강도가 다소 공격적이라는 지적과 `_image_to_pdf_bytes`가 `text.py`와 중복이라는 지적은 각각 "실제 사진으로 육안 검수 권장"(시각적 파라미터 튜닝 문제, 자동 테스트로 커버 불가), "Phase3에서 세 번째 processor(`score.py`)가 같은 패턴을 또 복붙하면 그때 공통 유틸로 추출"(지금은 6줄짜리 중복이라 과설계 방지 원칙상 보류)로 판단해 이번엔 반영하지 않음.
- 최종 검증: `pytest -q` → 84 passed, 2 skipped(기존과 동일한 의도된 결과). `ruff check .` → 통과.

### ✅ Phase2-3: 도형 벡터화 옵션 + 한계 고지 — 완료

- `pyproject.toml`에 `vtracer==0.6.15`를 신규 의존성으로 추가(Phase별 의존성 도입 원칙에 따라 이번 착수 시점에 추가).
- `python-dev-expert`가 구현: `app/processors/diagram.py`에 `vectorize_diagram(image, output_svg, **vtracer_params)`(vtracer의 `convert_raw_image_to_svg`로 PNG 바이트를 직접 넘겨 임시 파일 없이 SVG 생성) 추가, `DiagramResult`에 `svg_path`/`vectorization_disclaimer` 필드 추가, `process_image`에 `vectorize: bool = False` 옵션 추가(기본값은 벡터화 미실행, DIA-2 "사용자가 요청 시" 충족). `VECTORIZATION_DISCLAIMER` 상수(DIA-3 한계 고지 문구, "PPTX 수준의 완전 재편집이 아니다")를 처리기 계층에 준비해 Phase2-4에서 GUI가 그대로 가져다 쓸 수 있게 함 — 이번 태스크는 GUI 위젯 자체를 만들지 않음(로드맵이 DIA-3(UI)을 Phase2-4로 이미 분리해둠).
- `code-reviewer`가 검토: 차단급 문제 없음. vtracer 실제 API 시그니처와 호출 키워드 인자가 정확히 일치함을 `inspect.signature`로 직접 재확인, DIA-2(기본값 미실행)/DIA-3(GUI 분리 경계) 요구사항 부합 확인, `_PROCESSOR_REGISTRY` 하위 호환성 문제 없음 확인. 경미한 지적 4건은 모두 차단 사유가 아니라고 판단해 이번엔 반영하지 않음: (1) vtracer 파라미터 12개를 전부 시그니처에 노출한 것은 다소 앞서간 확장이나 얕은 파라미터 통과라 실질 비용 낮음, (2) PNG 인코딩 3줄 블록이 같은 파일 내에서 두 번째로 중복되나 6줄 미만이라 보류, (3) `output_svg` 기본 경로(`Path(output_pdf).with_suffix(".svg")`)가 `output_pdf`에 이미 `.svg` 확장자가 들어오면 방금 쓴 PDF를 조용히 덮어쓸 수 있음 — **Phase2-4에서 GUI가 파일명을 생성할 때 `.pdf` 확장자가 항상 보장되는지 반드시 확인할 것**, (4) roadmap 서술 섹션 누락(이 커밋으로 보완).
- 최종 검증: `pytest -q` → 87 passed, 2 skipped(기존과 동일한 의도된 결과). `ruff check .` → 통과.

### ✅ Phase2-4: GUI에 도형 처리 경로 연결 — 완료 (Phase2 도형 파이프라인 전체 완료)

- `python-dev-expert`가 구현: `app/router/dispatch.py`의 `_PROCESSOR_REGISTRY`에 `DocumentType.DIAGRAM`을 등록. `app/gui/worker.py`의 `ProcessingWorker`를 텍스트 하드코딩에서 라우팅 인식형으로 전면 재작성(이미지별로 전처리→`classify_document_type`→`route_and_process`), `PageResult`에 `document_type`/`sharpened_image`/`svg_path`/`vectorization_disclaimer` 필드를 기존 필드 호환을 유지한 채 추가. 신설 `VectorizeWorker(QThread)`로 DIA-2 벡터화를 별도 백그라운드 스레드로 분리(이미 선명화된 이미지 재사용). `app/gui/main_window.py`에 도형 페이지 전용 검수 안내 문구, "도형 벡터화" 버튼 + 상시 라벨(DIA-3 한계 고지를 팝업+라벨 두 채널로 노출) 추가.
- `code-reviewer`가 검토해 MEDIUM 2건 발견: (1) 배치 중 한 페이지만 미구현 유형(SCORE)으로 분류돼도 배치 전체가 완전 실패하고 부분 저장도 불가능하던 문제(줄무늬 배경의 SCORE 오탐 시 실제 발생 가능) — 페이지 단위 실패를 격리해 성공한 페이지만으로도 병합·저장 가능하게 수정, `failed_pages`로 실패 요약을 사용자에게 안내. (2) 벡터화 완료/실패 콜백이 클릭 당시 페이지 기준으로 화면을 갱신해 선택이 바뀐 사이 다른 페이지에 잘못된 상태가 노출되던 문제 — `_is_currently_selected` 가드로 데이터는 항상 갱신하되 화면 갱신만 조건부로 수정. 재검토에서 에러 팝업만 이 가드가 빠진 비대칭을 추가로 발견해(성공 팝업은 가드됨) 반영: 선택된 페이지가 아니면 팝업 대신 상태표시줄에 조용히 안내.
- 최종 검증: `pytest -q` → 96 passed, 3 skipped(MuseScore·Real-ESRGAN 가중치·oemer 체크포인트 미설치, 기존과 동일한 의도된 결과). `ruff check .` → 통과.
- **Phase2(도형/그래프 처리 + 유형 라우팅 도입) 핵심 파이프라인 전체 완료.** 남은 건 Phase2-5(End-to-End 검증).

### ✅ Phase3-1: 악보 OMR 인식 (oemer 연동) — 완료

- **환경 이슈(실제 재현·해결)**: `oemer==0.1.8`이 PyPI 메타데이터상 `onnxruntime-gpu`(macOS 배포판 없음)를 하드 의존성으로 선언해 `pip install oemer`가 이 머신에서 그대로 실패함을 확인. oemer 코드 자체는 `import onnxruntime`만 하므로 CPU용 `onnxruntime` 설치 후 `pip install oemer==0.1.8 --no-deps`로 우회 가능함을 검증(사용자 승인). `pyproject.toml`의 일반 `dependencies`에는 oemer가 정상 설치되는 `onnxruntime==1.29.0`/`scikit-learn==1.9.0`/`typing-extensions==4.16.0`/`matplotlib==3.11.1`/`scipy==1.18.1`만 추가하고, `oemer` 본체는 `scripts/install_oemer.py`(기존 `scripts/patch_basicsr.py`와 같은 idempotent 후속 설치 스크립트) + `README.md` 절차로 별도 처리.
- `python-dev-expert`가 구현: `app/processors/score.py`(`recognize_score`/`recognize_score_file` — `oemer.ete.extract()`를 실제 CLI 파서와 동일한 `argparse.Namespace`로 호출, 체크포인트 부재 시 `ScoreModelUnavailableError`로 명확히 실패, `ete.clear_data()`로 oemer 전역 상태 초기화 후 호출). `tests/processors/test_score.py`(체크포인트 없을 때 예외 발생 검증 — 이 머신에서 실제 exercise됨, 체크포인트 있을 때 MusicXML 유효성 검증은 skip).
- `code-reviewer`가 검토: `argparse.Namespace` 필드와 체크포인트 경로가 실제 oemer 소스와 정확히 일치함을 직접 대조 확인, 레이스 컨디션/색공간 문제 없음 확인. MEDIUM 1건(예외 메시지가 존재하지 않는 `install_oemer.sh`를 가리킴, 실제 파일은 `.py`) 발견해 즉시 수정. LOW 3건(roadmap 갱신 누락 — 이 커밋으로 보완, "파일 읽기+전처리" 5줄 관용구가 `text.py`/`diagram.py`에 이어 3번째로 복붙됨 — 아직 6줄 미만이라 보류, 체크포인트 확인이 `unet_big`만 검사하고 `seg_net`은 안 함 — oemer 자체의 기존 한계를 물려받은 것이라 이번 구현 결함 아님)는 차단 사유 아니라고 판단해 이번엔 반영하지 않음.
- SCR-2(재조판 PDF, MuseScore 연동)와 라우터 등록(`_PROCESSOR_REGISTRY`에 SCORE 추가)은 의도적으로 범위 밖 — 아직 처리기가 PDF를 만들지 못해 등록해도 의미가 없음(Phase3-2 이후).
- 최종 검증: `pytest -q` → 96 passed, 3 skipped(MuseScore·Real-ESRGAN 가중치·oemer 체크포인트 미설치, 기존과 동일한 의도된 결과). `ruff check .` → 통과.

### ✅ Phase2-5: Phase2 End-to-End 검증 — 완료 (Phase2 전체 완료)

- `qa-test-engineer`가 `tests/gui/test_e2e_phase2.py`에 §9 Phase2 수용 기준("도형 샘플로 텍스트와 동일한 end-to-end 확인")을 검증하는 테스트를 작성. `synthetic_diagram_photo`(왜곡·저해상도 합성 도형 이미지)를 실제 `MainWindow`를 통해 입력(GUI-1)→백그라운드 처리(QThread, 자동 분류로 실제 `DocumentType.DIAGRAM` 판정 확인)→미리보기(GUI-2)→도형 전용 검수 안내(GUI-3)→벡터화 버튼 클릭 후 SVG 생성 및 한계 고지 노출(DIA-2/3)→저장(GUI-4)까지 한 흐름으로 잇고, 저장된 PDF가 유효하며 텍스트 레이어가 없음(도형은 TXT-2와 무관)을 확인. 악보(score) 샘플 E2E는 SCR-2/3과 GUI 연결이 아직 없어 이번 범위에서 제외, Phase3-5로 미룸.
- 별도로 발견된 프로덕션 코드 결함 없음 — 테스트가 첫 실행에 통과.
- **환경 이슈 발견 및 해결(MuseScore 4 headless 실행)**: 이 태스크 진행 중 사용자 승인을 받아 `brew install --cask musescore`로 MuseScore 4를 설치했는데, 그 직후 기존에 skip 처리되던 악보 fixture(`tests/fixtures/synthetic.py`)가 처음으로 실제 실행되면서 두 가지 환경 문제가 실제로 재현됐다: (1) pytest-qt용 `QT_QPA_PLATFORM=offscreen`이 `mscore` 자식 프로세스에 그대로 상속되면 MuseScore가 번들한 Qt에는 "offscreen" 플랫폼 플러그인이 없어("cocoa"만 있음) 즉시 크래시함 — `_musescore_subprocess_env()`로 자식 프로세스 환경에서 이 변수를 제거해 해결. (2) 그 문제를 고친 뒤에도, 이 macOS 환경에서 MuseScore 4가 PNG를 정상적으로 다 쓴 *뒤에* 자체 크래시 리포터(Crashpad) 종료 경로에서 SIGABRT로 죽는 현상이 재현됨(GUI 세션 없이 headless로 반복 실행할 때 흔한 셧다운 버그로 보이며 렌더링 자체의 실패가 아님, 실제로 종료코드와 무관하게 유효한 PNG 파일이 만들어져 있음을 확인) — `subprocess.run`의 `check=True`를 제거하고 실제 출력 파일 존재 여부로 성공을 판단하도록 수정. 두 수정 모두 `tests/fixtures/synthetic.py`에 반영.
- 이 수정 이후 이전까지 MuseScore 미설치로 항상 skip되던 `tests/fixtures/test_synthetic.py::test_score_photo_via_fixture_or_skips`가 이제 실제로 통과함을 확인(스킵 3건 → 2건, 남은 2건은 오emer 체크포인트 미설치와 Real-ESRGAN 가중치 미지정으로 의도된 결과).
- 최종 검증: `pytest -q` → 98 passed, 2 skipped(오emer 체크포인트 미설치·Real-ESRGAN 가중치 미지정, 의도된 결과). `ruff check .` → 통과.
- **Phase2(도형/그래프 처리 + 유형 라우팅 도입) 전체 완료.** 다음은 Phase3(악보 처리) 계속 — Phase3-1(악보 OMR)은 이미 완료(위 참고), 남은 건 Phase3-2(재조판 PDF, MuseScore 연동)부터.

### ✅ Phase3-2: 재조판 PDF 생성 (MuseScore 연동) — 완료

- `python-dev-expert`가 `app/processors/score.py`에 SCR-2 구현 추가: `retypeset_score(musicxml_path, output_pdf, *, mscore_path=None, timeout=120.0)` — `mscore -o output.pdf input.musicxml`을 `subprocess.run([...], shell=False, check=False)`로 호출하고, Phase2-5에서 발견한 MuseScore headless 크래시 리포터 종료 문제(SIGABRT여도 출력 파일은 정상 생성됨)를 반영해 종료 코드가 아니라 실제 출력 파일로 성공을 판단. `find_musescore_executable()`/`_musescore_subprocess_env()`(QT_QPA_PLATFORM 제거)를 프로덕션 코드에 독립 구현(테스트 코드를 프로덕션이 import할 수 없다는 계층 규칙 때문에 `tests/fixtures/synthetic.py`와 의도적으로 중복). `ScoreResult`, `process_image`/`process_image_file`로 SCR-1(OMR)과 SCR-2(재조판)를 연결.
- `code-reviewer`가 검토해 HIGH 1건 발견 및 실제 재현: 같은 `output_pdf` 경로로 재호출했을 때 mscore가 완전히 실패해도 이전 호출이 남긴 유효한 PDF를 "성공"으로 오인하는 조용한 버그(파일 존재+크기만으로 성공을 판단하는 로직의 근본 결함) — mscore 실행 직전에 기존 출력 파일을 무조건 삭제해 해결(별도 mtime 비교 로직 없이 단순하게 해결). MEDIUM 1건(깨진 MusicXML 입력 시 timeout까지 행(hang)한 뒤 raw `TimeoutExpired`가 그대로 전파) — `ScoreRenderingError`로 감싸서 사용자가 원인을 알 수 있게 수정. LOW 1건(실패 시 mscore stdout/stderr가 로그에 전혀 안 남음) — 실패 경로에서만 `logger.warning`으로 남기도록 수정. 세 건 모두 회귀 테스트 추가로 검증.
- 최종 검증: `pytest -q` → 106 passed, 2 skipped(oemer 체크포인트 미설치·Real-ESRGAN 가중치 미지정, 의도된 결과). `ruff check .` → 통과.

## 다음 진행 방식

- 담당 에이전트: 구현은 `python-dev-expert`, 테스트는 `qa-test-engineer`, 진행상황 총괄은 `product-manager`, 커밋 전 검토는 `code-reviewer`.
- 실행 순서는 각 Phase 표의 순서를 따르되, Phase2와 Phase3는 서로 병렬 진행 가능(둘 다 Phase2-1에만 의존), Fixtures-1은 Phase1-1 직후·Phase1-2 이전에 실행.
- Task 실행: Shrimp의 `execute_task <ID>` 사용 권장 (자동으로 `verify_task`까지 유도됨).
