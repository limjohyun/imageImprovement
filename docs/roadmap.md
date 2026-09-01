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
| 3 | 악보 오류 검수 경로 (외부 편집기 열기, 동일하게 MuseScore 설치 필요) | SCR-3 | #2 | `59367417` | ✅ 완료 |
| 4 | GUI에 악보 처리 경로 연결 | — | #3 | `0deef3cf` | ✅ 완료 |
| 5 | Phase3 End-to-End 검증 | §9 Phase2/3 | #4 | `96bc862b` | ✅ 완료 |

## Phase 4 — GUI 고도화

| # | Task | 요구사항 ID | 의존 | ID | 상태 |
|---|---|---|---|---|---|
| 1 | 수동 보정 (자르기/회전) | GUI-3(일부) | Phase2#5, Phase3#5 | `851d5923` | ✅ 완료 |
| 2 | 도형/악보 검수 위젯 통합 | GUI-3(전체) | #1 | `32dc96c8` | ✅ 완료 |
| 3 | 페이지 재정렬/삭제 | PDF-2 | #2 | `6a46cdf1` | ✅ 완료 |
| 4 | 유형 자동 라우팅 정교화 | RT-1,2(고도화) | #3 | `9d32a092` | ✅ 완료(부분 범위 축소) |
| 5 | Phase4 End-to-End 검증 (혼합 워크플로우) | §9 Phase4 | #4 | `1abca8b7` | ✅ 완료 |

## Phase 5 — 선택적 클라우드 백업 (낮은 우선순위)

핵심 파이프라인 완성 후 진행하는 부가 기능. 오프라인 목표(§2)와 상충하지 않도록 opt-in.

| # | Task | 요구사항 ID | 의존 | ID | 상태 |
|---|---|---|---|---|---|
| 1 | 로컬 저장 우선 보장 + 백업 설정 UI(기본 off) | BKP-1 | Phase4#5 | `90830178` | ✅ 완료 |
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

### ✅ Phase3-3: 악보 오류 검수 경로 (외부 편집기 열기) — 완료

- `python-dev-expert`가 `app/processors/score.py`에 SCR-3 구현 추가: `open_score_in_external_editor(musicxml_path, *, mscore_path=None)` — MuseScore CLI를 `-o` 옵션 없이 파일 경로만 넘겨 GUI 모드로 실행(`subprocess.Popen`, 완료를 기다리지 않고 즉시 반환). Phase3-2의 `find_musescore_executable()`/`_musescore_subprocess_env()`/`ScoreRendererUnavailableError`를 재사용(새로 만들지 않음). 재수정된 MusicXML을 다시 감지/수집하는 로직은 의도적으로 범위 밖(MuseScore가 같은 파일 경로를 직접 갱신하는 것으로 충분, GUI의 "다시 재조판" 버튼 등은 Phase3-4 몫).
- `code-reviewer`가 검토: 차단급 문제 없음. 비블로킹 보장(`.wait()`/`.communicate()` 없음, 실제 5초 sleep 프로세스로 2초 이내 반환 검증) 확인, 재수정 반영 흐름 생략 판단 타당함 확인. 경미한 지적 3건(반환된 `Popen` 참조를 호출자가 안 들고 있으면 GC 시 `ResourceWarning` 발생 가능 — Phase3-4에서 GUI가 위젯 attribute로 참조를 유지해야 함을 유의, MuseScore 미발견 예외 처리 코드가 `retypeset_score`와 3~5줄 중복 — 세 번째 호출부가 생기면 헬퍼로 추출 고려, `Popen` 자체의 `OSError` 미처리 — `retypeset_score`도 동일한 기존 패턴이라 새로운 비일관성 아님)는 모두 정보성/Phase3-4에서 다룰 사항으로 판단해 이번엔 반영하지 않음.
- 최종 검증: `pytest -q` → 110 passed, 2 skipped(oemer 체크포인트 미설치·Real-ESRGAN 가중치 미지정, 의도된 결과). `ruff check .` → 통과.

### ✅ Phase3-4: GUI에 악보 처리 경로 연결 — 완료 (Phase3 악보 파이프라인 전체 완료)

- `python-dev-expert`가 Phase2-4(도형 GUI 연결)와 동일한 패턴으로 구현: `app/router/dispatch.py`의 `_PROCESSOR_REGISTRY`에 `DocumentType.SCORE: score_processor.process_image` 등록. `app/gui/worker.py`의 `PageResult`에 `musicxml_path: Path | None = None` 필드를 추가하고, `route_and_process`가 `ScoreResult`를 반환하면 이를 채우는 분기를 `TextOcrResult`/`DiagramResult`와 같은 형태로 추가 — 기존 per-page 실패 격리 로직(`failed_pages` 누적)이 그대로 적용되어, 이 개발 머신처럼 oemer 체크포인트가 없어 `ScoreModelUnavailableError`가 나는 페이지도 나머지 페이지 처리를 막지 않음. `app/gui/main_window.py`에 `_build_score_group()`(악보 전용 검수 안내 + "MuseScore에서 열기" 버튼, `PageResult.musicxml_path`가 설정된 경우에만 활성화)과 `_on_open_in_musescore_clicked()`를 추가하고, `open_score_in_external_editor`가 즉시 반환하는 `subprocess.Popen`을 `self._open_musescore_processes` 리스트에 보관해 `ResourceWarning`을 방지. RT-1 수동 오버라이드 UI는 계획대로 Phase4-4로 범위 밖 유지.
- 진행 중 인프라 이슈(코드 결함 아님): 구현/리뷰 에이전트가 각각 한 번씩 "600초간 진행 없음(stream watchdog)"으로 stall되어 실패 보고가 왔으나, 실제 파일 변경은 정상적으로 디스크에 반영되어 있었음을 직접 확인(구현 완료 상태였음). 이어서 `pytest` 전체 실행 시 `retypeset_score` 관련 4건이 실패했는데, 원인은 코드가 아니라 `/Applications/MuseScore 4.app`이 (원인 불명으로) 휴지통으로 이동되어 있었고 brew의 `mscore` 심볼릭 링크가 깨져 있었던 것 — 휴지통에서 앱을 복원하고, 이동 과정에서 다시 붙은 `com.apple.quarantine` 속성을 제거해 해결(둘 다 로컬 환경 문제, 코드 변경 없음).
- `code-reviewer`가 새 에이전트로 재검토(이전 리뷰 에이전트는 stall로 결과 없이 실패): 차단급(HIGH) 문제 없음. MEDIUM 1건 — `_on_open_in_musescore_clicked`가 `ScoreRendererUnavailableError`/`FileNotFoundError`만 잡고 `Popen`이 던질 수 있는 일반 `OSError`(예: 손상된 바이너리 실행 권한 오류)는 처리하지 않음, Phase3-3 리뷰 시점에 이미 "Phase3-4에서 다룰 사항"으로 이월돼 있던 항목이라 이번에 반영 — `except OSError`로 확장해 `QMessageBox.critical`로 노출. LOW 3건 중 실제 코드로 반영한 것은 1건(`self._open_musescore_processes`가 종료된 프로세스도 계속 쌓여 무한정 커질 수 있음 — 클릭할 때마다 `p.poll() is None`으로 필터링해 정리). 나머지 2건(MuseScore에서 저장한 수정본을 앱에 다시 반영하는 "재조판" 흐름 부재는 코드 결함이 아니라 스코프 확인 사항으로 Phase4-2 검토 대상으로 남김, 버튼 연타 시 MuseScore 인스턴스가 중복 실행될 수 있는 점은 정보성으로 남김)는 PRD/roadmap 요구사항이 아니고 이 개인용 도구 특성상 리스크가 낮아 반영하지 않음.
- 최종 검증: `pytest -q` → 116 passed, 2 skipped(oemer 체크포인트 미설치·Real-ESRGAN 가중치 미지정, 의도된 결과). `ruff check .` → 통과.

### ✅ Phase3-5: Phase3 End-to-End 검증 — 완료 (Phase3 전체 완료)

- `qa-test-engineer`가 `tests/gui/test_e2e_phase3.py`에 §9 Phase3 수용 기준을 검증하는 테스트 2건을 작성. (1) `test_phase3_end_to_end_distorted_score_photo_to_pdf`: Phase2와 동일한 패턴으로 악보 샘플을 실제 `MainWindow`에 입력→처리→자동 분류(`DocumentType.SCORE`)→미리보기→악보 전용 검수 UI("MuseScore에서 열기" 버튼 활성화 확인, 실제 클릭은 하지 않음)→저장까지 잇는 정식 happy-path지만, 이 머신엔 oemer 체크포인트가 없어 `pytest.skip`(체크포인트가 준비된 머신/CI에서만 실제 실행). (2) `test_phase3_gracefully_isolates_score_page_when_checkpoint_missing`: 이 머신의 실제 현실(체크포인트 없음) 그대로 텍스트+악보 샘플을 함께 입력해, 텍스트는 성공·악보는 `ScoreModelUnavailableError`로 페이지 격리되는 부분 성공 흐름이 크래시 없이 끝까지 도는지 실제로 검증 — 이 테스트는 이 머신에서 실제로 PASS함.
- Phase2-5와 마찬가지로 테스트 전용 변경(프로덕션 코드 수정 없음)이라 별도 `code-reviewer` 단계 없이 진행. 발견된 프로덕션 결함 없음.
- 최종 검증: `pytest -q` → 117 passed, 3 skipped(oemer 체크포인트 미설치 2건 + Real-ESRGAN 가중치 미지정 1건, 모두 기존/의도된 결과). `ruff check .` → 통과.
- **Phase3(악보 처리, OMR) 전체 완료.**

### ✅ Phase4-1: 수동 보정 (자르기/회전) — 완료

- `python-dev-expert`가 구현: `app/preprocess/manual_correction.py`(신규) — `rotate_image`(90도 단위), `crop_image`(x/y/width/height 범위 검증), `apply_manual_correction`(회전 먼저 → 자르기 순서, Qt 비의존 순수 함수). `app/gui/crop_rotate_dialog.py`(신규) — `CropRotateDialog`: 마우스 드래그 대신 숫자 입력(회전 콤보박스 + x/y/width/height 스핀박스) 방식으로 사용자와 합의(구현 단순성·pytest-qt 자동화 용이성). `app/gui/worker.py`의 `ProcessingWorker._process_one` 로직을 모듈 함수 `process_page_image()`로 추출해 신설된 `ReprocessWorker(QThread)`와 공유(중복 제거). `app/gui/main_window.py`에 문서 유형 무관 공통 "자르기/회전 보정" 그룹박스 추가, 재처리는 항상 raw 원본에서 다시 시작(누적 크롭/undo 스택 없음 — 의도된 범위 축소), 완료 시 Phase2-4의 `_is_currently_selected` 가드 패턴으로 화면 갱신, `_rebuild_merged_pdf()`로 최종 PDF 재병합.
- `code-reviewer`가 검토해 HIGH 2건 발견 및 코드 추적으로 실제 재현 가능함을 확인: (1) 배치 처리(`ProcessingWorker`) 도중 이미 끝난 페이지를 재처리하면 `_rebuild_merged_pdf()`와 배치의 최종 `assemble_pdf`가 같은 `merged.pdf` 경로에 동시에 쓸 수 있는 경합 — `_refresh_crop_rotate_panel`이 페이지 결과 유무만 보고 배치가 아직 실행 중인지 확인하지 않아 발생. (2) `_start_processing()`이 `self._vectorize_worker`/`self._reprocess_worker` 실행 여부를 확인하지 않아, 재처리/벡터화가 진행 중일 때 "처리 시작"을 다시 누르면 `shutil.rmtree`가 그 워커가 곧 쓰려는 작업 디렉터리를 삭제해버림(`closeEvent`는 이미 여러 워커를 확인하는데 여기만 빠짐). MEDIUM 1건 — 재처리 완료 콜백이 `self._reprocess_worker`를 콜백 내부에서 다시 참조해, 좁은 시간창에 새 재처리가 시작되면 먼저 시작된 워커의 뒤늦은 콜백이 새 워커의 상태를 잘못 정리할 수 있는 TOCTOU 경합.
- `python-dev-expert`가 수정: `_running_background_workers()` 헬퍼로 세 워커(`_worker`/`_vectorize_worker`/`_reprocess_worker`)의 실행 여부를 한 곳에서 계산해 `_start_processing()`과 `closeEvent()`(수정 중 `closeEvent`가 실제로는 `_reprocess_worker`를 빼먹고 있던 것도 추가로 발견해 함께 고침) 양쪽에서 재사용. 자르기/회전 버튼은 배치/재처리 중 하나라도 실행 중이면 비활성화, 배치 완료 시점에 재갱신. 재처리 완료/에러 콜백은 `self._reprocess_worker`를 다시 읽는 대신 콜백을 발생시킨 워커 인스턴스를 클로저로 그 자리에서 고정해 전달하고, `self._reprocess_worker is worker`일 때만 상태를 정리하도록 변경. `VectorizeWorker` 쪽에도 이론상 동일한 TOCTOU 취약점이 있음을 확인했으나 이번 커밋 범위(Phase4-1 신규 코드) 밖이라 별도 과제로 남김. 회귀 테스트 `tests/gui/test_crop_rotate_guards.py`(6건) 신규 추가.
- 최종 검증: `pytest -q` → 143 passed, 3 skipped(oemer 체크포인트 미설치 2건 + Real-ESRGAN 가중치 미지정 1건, 기존과 동일한 의도된 결과). `ruff check .` → 통과.

### ✅ Phase4-2: 도형/악보 검수 위젯 통합 — 완료

- 범위는 사용자와 사전 합의: **UI 통합/정리만**(새 기능 추가 없음). `python-dev-expert`가 `app/gui/main_window.py`만 수정: 문서 유형 무관 공통 영역(자르기/회전)은 오른쪽 컬럼 최상단에 그대로 고정하고, 유형별 전용 패널(텍스트 검수/도형 벡터화/악보 MuseScore)은 `_build_review_stack()`으로 신설한 `QStackedWidget`(`self.review_stack`) 안에 페이지로 등록해 `_show_review_page_for(document_type)`가 현재 페이지 유형에 맞는 것 하나만 보여주도록 변경(기존엔 세 그룹박스가 항상 동시에 화면에 남아있었음). 기존 위젯 객체 이름(`text_review_edit`, `vectorize_button`, `open_in_musescore_button` 등)과 기능은 전혀 바꾸지 않음.
- `code-reviewer`가 검토: 차단급(HIGH) 문제 없음. `QStackedWidget` 전환 로직을 별도 스크립트로 직접 재현해 문서 유형별 페이지 전환이 정확하고 숨겨진 페이지 위젯이 클릭 불가능한 상태로 유지됨을 확인. MEDIUM 2건 — (1) 스택 전체에 `stretch=1`을 준 탓에 도형/악보처럼 컴팩트한 페이지도 `QStackedWidget`이 강제로 늘려 그룹박스 아래 500px 가까운 빈 공간이 생기는 실제 시각적 회귀(실측으로 재현 확인). (2) `review_stack.currentWidget()`이 올바른지 검증하는 회귀 테스트가 전무해 전환 로직이 완전히 잘못돼도 기존 테스트가 못 잡아내는 커버리지 공백.
- `python-dev-expert`가 수정: 도형/악보 그룹박스를 스택에 직접 넣지 않고 `_wrap_with_top_stretch()` 헬퍼로 `QVBoxLayout`+`addStretch(1)` 래퍼에 담아 등록해, 그룹박스는 위쪽에 자연스러운 크기로 고정되고 남는 공간은 테두리 밖 배경으로 빠지게 함(텍스트 검수 패널은 원래대로 확장 유지). `tests/gui/test_main_window.py`에 `test_review_stack_shows_page_matching_document_type` 추가— TEXT/DIAGRAM/SCORE 세 유형 선택 시 `review_stack.currentWidget()`이 기대한 페이지와 정확히 일치하는지 검증.
- 최종 검증: `pytest -q` → 144 passed, 3 skipped(기존과 동일한 의도된 결과). `ruff check .` → 통과.
- **참고(추적 유지)**: Phase3-4 리뷰에서 "MuseScore 재수정본을 앱에 재반영하는 흐름"이 Phase4-2 검토 대상으로 이월된 바 있으나, 이번 Phase4-2는 UI 통합만으로 범위를 좁히기로 사용자와 합의했으므로 그 항목은 이번에도 구현하지 않음 — 필요 시 별도 task로 재검토.

### ✅ Phase4-3: 페이지 재정렬/삭제 — 완료

- `python-dev-expert`가 구현: `file_list_widget`에 `QAbstractItemView.DragDropMode.InternalMove`로 드래그 재정렬 지원, 내부 모델의 `rowsMoved`를 `_on_rows_moved()`에 연결해 처리된 페이지가 있으면 Phase4-1의 `_rebuild_merged_pdf()`를 그대로 재사용해 새 순서로 재병합. "선택한 페이지 삭제" 버튼 + `Delete`/`Backspace` 키로 `_on_delete_pages_clicked()` 트리거, 목록/`_results_by_input`에서 제거 후 재병합(마지막 페이지 삭제 시 GUI-1 이전 초기 상태로 복귀). `_running_background_workers()`(Phase4-1)를 재사용해 배치/벡터화/재처리 중에는 드래그·삭제를 막는 `_refresh_list_editing_controls()` 도입.
- `code-reviewer`가 검토해 HIGH 1건 발견 및 재현 스크립트로 실제 검증: `_refresh_list_editing_controls()` 호출이 `self._worker = worker` 직후·`worker.start()` **이전**에 위치해, `QThread.isRunning()`이 `.start()` 호출 전엔 항상 `False`라는 사실 때문에 배치/벡터화/재처리 시작 시점의 드래그·삭제 가드가 실질적으로 무력화되는 문제(세 곳 `_start_processing`/`_on_vectorize_clicked`/`_on_crop_rotate_clicked` 전부 동일 패턴) — 처리 도중 드래그로 순서를 바꾸면 화면 목록 순서와 실제 저장될 병합 PDF 순서가 조용히 어긋난 채 남을 수 있음(완료 콜백이 재병합을 하지 않으므로). 기존 회귀 테스트 3건은 `_worker`에 이미 시작된 것으로 가정한 가짜 스레드를 직접 대입하는 방식이라 이 타이밍 버그를 전혀 잡아내지 못함을 지적.
- `python-dev-expert`가 수정: 세 호출부 모두 `_refresh_list_editing_controls()` 호출을 `worker.start()` **이후**로 이동. `_start_processing()`을 실제로 호출해 `.start()` 직후 시점의 드래그·삭제 가드 상태를 검증하는 통합 회귀 테스트(`test_start_processing_disables_editing_immediately_after_start`) 신규 추가(수정 전 순서로는 실패함을 확인).
- 진행 중 발견된 별개 환경 이슈(코드 결함 아님, 이번 범위 밖): `synthetic_score_photo` fixture가 부르는 `mscore` 서브프로세스 호출이 시스템 부하가 높을 때(동시에 여러 pytest 프로세스가 돌 때) `timeout` 이후 자식은 죽지만 손자(MuseScore GUI 앱 본체)가 파이프 fd를 물고 있어 `subprocess.run`의 `communicate()`가 무한 대기하는 것으로 추정되는 hang을 관찰함 — `tests/fixtures/synthetic.py` 관련, 이번 커밋 범위 밖이라 손대지 않고 기록만 남김.
- 최종 검증: 신규/관련 회귀 테스트 `tests/gui/test_page_reorder_delete.py` 13개 전부 통과. `tests/gui/` 전체(위 환경 이슈로 느린 악보 E2E 3개 제외) 52 passed. `ruff check .` → 통과.

### ✅ Phase4-4: 유형 자동 라우팅 정교화 — 완료(부분 범위 축소)

- Phase2-1에서 알려진 한계로 남겨뒀던 오탐 시나리오 3건 중 2건을 `python-dev-expert`가 수정: (1) 줄무늬 배경(커튼/벽지 등 등간격 평행선) → SCORE 오탐은 오선 후보 대역 안에 음표머리 등 "선이 아닌" 내용이 실제로 있는지 확인하는 `_has_non_line_content_near`로 해결, (2) 텍스트 라벨 없는 단일 대형 도형 → TEXT 오탐은 큰 컴포넌트가 정확히 하나뿐이고 글자 크기 컴포넌트가 전혀 없을 때만 예외적으로 DIAGRAM으로 판정하는 엄격한 조건을 추가해 해결. 두 수정 모두 `code-reviewer` 검토 통과(회귀 없음).
- 세 번째 남은 오탐(표/격자 문서 → DIAGRAM)은 두 차례 재설계했으나 모두 새 HIGH급 회귀가 발견되어 **이번 Phase 범위에서 제외하기로 결정**(사용자 확인): 1차(큰 컴포넌트 면적의 변동계수로 "표 셀 vs 반복 도형" 구분)는 실사진 지터에 취약해 표를 다시 DIAGRAM으로 오분류, 셀 4개 미만 소형 표는 검사 자체를 건너뜀, 균일 크기 반복 도형 4개 이상이 새로 TEXT로 오분류되는 반대 방향 회귀까지 3건의 HIGH가 나옴. 2차(`cv2.HoughLinesP`로 실제 격자선 존재 여부를 직접 검출)는 1차의 3가지 반례를 모두 해결했지만, 원근보정 후 잔여 기울기(6도 이상)에서 각도 임계값을 못 만족해 원래 버그가 재발하는 문제와 PRD가 명시하는 흔한 도형 레이아웃(2×2 사분면, 나란히 붙은 플로우차트 박스)이 표로 오판정되는 새 HIGH 2건이 나옴 — 순수 기하학적 휴리스틱으로는 "표 vs 격자형 배치 도형" 구분이 이 프로젝트 규모에서 수렴하지 않는다고 판단해 재설계 중단.
- RT-1 요구사항 자체가 "자동 추정 + 수동 오버라이드"이므로, 표→DIAGRAM 오탐은 이미 구현된 수동 오버라이드 UI(GUI에서 문서 유형을 직접 지정하는 콤보박스 + 적용 버튼, `type_override`를 `process_page_image`/`ReprocessWorker`까지 관통시킴)로 구제 가능한 **알려진 한계**로 문서화하고 넘어간다.
- 수동 오버라이드 UI(`app/gui/main_window.py`, `app/gui/worker.py`)는 `code-reviewer` 검토 통과(워커 경합·좌표계 문제 없음 확인) — 자르기/회전(Phase4-1)과 동일하게 재처리(`ReprocessWorker`) 경로에서만 적용되며, 최초 배치 처리(`ProcessingWorker`)는 계속 자동 분류만 사용.
- 최종 검증: `tests/router/test_classifier.py`, `tests/gui/test_crop_rotate_guards.py`, `tests/gui/test_worker_routing.py` 전부 통과. `ruff check .` → 통과.

### ✅ Phase4-5: Phase4 End-to-End 검증 (혼합 워크플로우) — 완료 (Phase4 전체 완료)

- `qa-test-engineer`가 `tests/gui/test_e2e_phase4.py`에 §9 Phase4 수용 기준("여러 유형이 섞인 입력 세트로 전체 워크플로우 수행")을 검증하는 테스트를 작성. Phase2-5/Phase3-5와 같은 패턴으로 실제 `MainWindow`를 통해 텍스트+도형 혼합 입력(GUI-1)→백그라운드 처리(자동 분류로 TEXT/DIAGRAM 각각 정확히 판정 확인)→문서 유형별 검수 UI 전환(GUI-3, Phase4-2)까지 잇고, 여기에 Phase4에서 새로 추가된 기능들이 실제로 맞물리는지를 이어서 검증: 도형으로 자동 분류된 페이지를 수동 오버라이드(RT-1, Phase4-4)로 TEXT로 되돌려 `ReprocessWorker`가 OCR까지 포함해 실제로 재처리하는지, 이후 첫 페이지를 삭제(PDF-2, Phase4-3)했을 때 목록/결과 캐시/병합 PDF가 올바르게 재구성되는지, 마지막으로 저장(GUI-4)된 PDF가 오버라이드+삭제를 모두 반영한 1페이지 상태인지까지 하나의 흐름으로 확인. 악보(score) 샘플은 Phase3-5와 동일한 이유(oemer 체크포인트 미설치)로 이번 혼합 시나리오에서 제외.
- 수동 오버라이드 시나리오를 포함한 것은 Phase4-4에서 "표→DIAGRAM 오탐을 수동 오버라이드로 구제하기로" 결정한 것을 실제 GUI 흐름 끝까지(재처리 파이프라인 포함) 한 번은 검증해두기 위함.
- 테스트 전용 변경(프로덕션 코드 수정 없음)이라 Phase2-5/Phase3-5 선례대로 별도 `code-reviewer` 단계 없이 진행. 발견된 프로덕션 결함 없음(도형 이미지를 강제로 OCR해도 Tesseract/OCRmyPDF가 예외 없이 빈 텍스트를 정상 반환하며 파이프라인이 끝까지 완주함을 확인).
- 최종 검증: `tests/gui/test_e2e_phase4.py` → 1 passed(Tesseract/Ghostscript/qpdf가 설치된 이 머신에서 skip 없이 실제 파이프라인 전체 실행). `ruff check .` → 통과.
- **Phase4(GUI 고도화) 전체 완료.** 다음은 Phase5(선택적 클라우드 백업, 낮은 우선순위) — 아직 시작 전.

### ✅ Phase5-1: 로컬 저장 우선 보장 + 백업 설정 UI(기본 off) — 완료

- `python-dev-expert`가 구현: 신규 `app/backup/` 패키지 — `settings.py`(`BackupSettings`, `QSettings` 기반으로 백업 활성화 여부를 저장/조회, 기본값 `False`, `qsettings` 인스턴스 주입 지점을 열어 테스트가 실제 사용자 프리퍼런스 파일을 건드리지 않게 함), `uploader.py`(`upload_pdf(pdf_path, *, document_type=None)` — 로그만 남기는 no-op 스텁, Phase5-2가 채울 자리). `app/gui/main_window.py` 툴바에 "백업 사용" 체크박스 추가(저장값으로 초기화 후 시그널 연결, 토글 시 `BackupSettings`에 즉시 영속화), `_on_save_clicked()`가 로컬 PDF 저장(`shutil.copy2`)이 예외 없이 끝난 뒤에만 `_attempt_backup()`을 호출하도록 순서 고정 — 백업이 꺼져 있으면 `upload_pdf` 호출 자체가 스킵되고(오프라인 보장), 켜져 있어도 호출을 `try/except Exception`으로 감싸 실패가 로컬 저장 결과·GUI 반응성에 전혀 영향을 주지 않게 함(BKP-1 핵심 계약). `supabase-py` 등 실제 업로드 의존성은 이번 태스크 범위 밖이라 추가하지 않음(Phase5-2 몫).
- `code-reviewer`가 검토: HIGH/MEDIUM 없음. 로컬 저장→백업 순서 역전 경로 없음, 예외가 `except Exception`으로 완전히 격리됨, 백업 off일 때 `upload_pdf` 호출 자체가 스킵됨(테스트로 검증됨), `QSettings` 사용이 이 프로젝트에서 유일하며 테스트가 격리된 인스턴스를 사용해 실제 사용자 설정을 오염시키지 않음을 확인. LOW 2건은 차단 사유 아니라고 판단해 반영하지 않음: (1) `app/backup/__init__.py`의 재노출 파사드가 현재 아무 호출부에서도 쓰이지 않음 — 그러나 `app/router/__init__.py`/`app/preprocess/__init__.py`와 동일한 기존 컨벤션이라 일관성 유지 차원에서 그대로 둠, (2) 백업 체크박스가 활성화 가능한데 실제로는 아직 아무 일도 하지 않는 것은 제품 관점의 논의 대상이나 툴팁으로 이미 정직하게 고지돼 있어 코드 결함 아님.
- 신규 테스트: `tests/backup/test_settings.py`(기본값 off, 저장/복원, bool 타입 캐스팅 확인), `tests/gui/test_backup_hook.py`(체크박스 기본값/토글 영속화, 백업 off일 때 `upload_pdf` 미호출, `upload_pdf`가 예외를 던져도 로컬 저장은 그대로 성공).
- 최종 검증: `pytest -q` → 167 passed, 3 skipped(MuseScore/Real-ESRGAN 가중치/oemer 체크포인트 미설치, 기존과 동일한 의도된 스킵). `ruff check .` → 통과.
- 다음 태스크(#2 Supabase 업로드, #3 자격증명 관리)는 각각 `app/backup/uploader.py`의 `upload_pdf` 시그니처와 `app/backup/settings.py`를 그대로 이어붙이면 된다.

### 🐛 버그 수정: 원근보정 코너 검출 오탐 (실사진 QA로 발견)

- 사용자가 제공한 실제 iPhone 사진(우쿨렐레 악보를 스크린으로 촬영, 4032x3024)으로 전체 파이프라인을 수동 테스트하던 중 발견: `detect_document_corners`(PRE-1)가 문서 페이지 전체가 아니라 악보 안의 오선+TAB 한 줄(가로로는 이미지 폭 전체, 세로로는 약 11%만 차지)을 문서 경계로 잘못 인식해, 원근보정 결과가 완전히 찌그러진 얇은 띠(약 467×2700px)로 잘리는 버그.
- 근본 원인: 기존 로직은 `min_area_ratio`(면적 비율)만 검사해, "가로는 꽉 차지만 세로는 극히 일부만 차지하는" 극단적으로 치우친 4각형도 면적 조건만 넘으면 통과시켰다(스크린 촬영이라 실제 페이지 외곽 대비가 약해 순위에서 밀려난 것으로 추정).
- `python-dev-expert`가 수정: `detect_document_corners`에 `min_dimension_ratio: float = 0.3` 파라미터 추가 — 후보 4각형의 `cv2.boundingRect` 기준 폭/높이가 각각 이미지 전체 폭/높이의 30% 이상이어야 통과. 조건을 만족하는 후보가 없으면 기존과 동일하게 `None`을 반환(→ `correct_perspective`가 `DocumentCornersNotFoundError`로 변환, 계약 유지). 실제 문제 사진으로 재검증: 수정 전 파라미터(0.0)로는 버그가 그대로 재현되고, 기본값(0.3)으로는 잘못된 얇은 좌표 대신 안전하게 `None`을 반환함을 확인.
- `code-reviewer`가 1차 검토에서 HIGH 1건 발견: 처음 작성된 회귀 테스트가 실제 문서 사각형(면적 大, 채워 그림)과 그 "안에" 포함된 가짜 얇은 사각형(면적 小)을 함께 그렸는데, 포함된 도형의 면적이 포함하는 도형보다 클 수 없다는 기하학적 모순 때문에 수정 전/후 코드 양쪽에서 항상 통과해 회귀 방어력이 없었음. `python-dev-expert`가 재설계: 진짜 문서 사각형은 그리지 않고 얇은 4각형 하나만 배치한 뒤, 같은 이미지에 `min_dimension_ratio=0.0`(구버전 재현, 검출됨)과 기본값(신버전, `None`)을 각각 호출해 인과관계를 직접 증명하도록 변경. 재검토 결과 HIGH/MEDIUM 없음.
- MEDIUM(참고, 미반영): 기본값 0.3의 실측 근거가 다양한 사진으로 sweep되지 않았고, 회전된(축에 정렬되지 않은) 얇은 사각형까지는 못 막는 잔여 한계가 있음 — 다만 실패 시에도 크래시가 아니라 안전한 `DocumentCornersNotFoundError` 폴백이라 심각도 낮음.
- 이번에 실사진 테스트로 함께 발견된 별개 이슈(오선+TAB 병기 악보가 SCORE로 자동분류되지 않음)는 사용자 지시로 이번 수정 범위에서 제외, 별도 로드맵 항목 없이 보류.
- 최종 검증: `tests/preprocess/ -q` → 48 passed, 1 skipped(기존과 동일한 의도된 스킵). `ruff check .` → 통과.

### 🐛 버그 수정: 조명보정이 실사진을 과도하게 어둡게 만드는 문제 (실사진 QA로 발견)

- 사용자가 결과 PDF를 직접 확인하고 "보정된 이미지가 너무 어둡다, 텍스트/악보처럼 검은 객체 위주 문서는 흑백 대비가 확실히 보이도록 해달라"고 지적. 실측: `correct_illumination`(PRE-3) 적용 후 실사진 평균 밝기가 157.6 → 48.4로 급락.
- 근본 원인: `_normalize_channel`이 `ratio = channel / (background+eps)`를 `cv2.normalize(..., NORM_MINMAX)`로 0~255에 매핑하는데, 실사진의 하이라이트 등 소수 이상치 픽셀 때문에 비율 최댓값이 정상 배경(중앙값 ~1.05)보다 훨씬 크게(최대 4.77) 튀어, min-max가 이 이상치를 기준으로 범위를 늘리면서 정상 배경 전체가 어두운 값으로 짓눌림.
- `python-dev-expert`가 수정: `cv2.normalize(...)`를 `np.clip(ratio * 255.0, 0, 255).astype(np.uint8)`로 교체 — 비율 1.0(배경)을 흰색 근처로 고정 앵커링하는 방식. 실사진 재검증: 원본 158.8 → 구버전 재현 76.3 → 신버전 236.9(중앙값 254)로 원본보다도 밝고 뚜렷한 흑백 대비 확보.
- `code-reviewer`가 검토: 새 회귀 테스트가 실제로 구버전에서 실패·신버전에서 통과함을 직접 재현 확인(유효한 회귀 테스트, 이번 세션의 원근보정 1차 회귀 테스트처럼 무력하지 않음). 추가로 "이상치가 없어도 min-max 자체가 배경을 충분히 희게 못 만드는" 더 근본적인 개선임을 발견(순수 어두운 사각형만 있는 이미지에서도 구버전 128.8 vs 신버전 255). MEDIUM 1건: `app/preprocess/`는 text/diagram/score가 공유하는 모듈인데, 이번 수정으로 "배경을 흰색에 가깝게 고정 앵커링"하는 동작이 더 강해져 도형/차트 사진에서 의도된 배경 음영(표 헤더 셀 음영 등)까지 하얗게 밀어버릴 가능성이 검증되지 않음(diagram 합성 fixture 테스트는 shape/dtype만 확인). 다만 이는 division normalization 기법 자체의 기존 설계 특성(구버전도 이미 일관성 없이 배경을 밝게 미는 경향이 있었음)이지 이번 수정이 새로 만든 회귀는 아니라고 판단해 차단 사유로 보지 않고, 실제 문제가 되면 그때 diagram 경로에 별도 대응(예: 커널/스케일 파라미터 분리)을 검토하기로 하고 지금은 반영하지 않음.
- 최종 검증: `tests/preprocess/ -q` → 51 passed, 1 skipped(기존과 동일한 의도된 스킵). `ruff check .` → 통과.

### 🔧 PRE-1 원근보정 실사진 대응 계획 수립 및 Task1(deskew 강건성 개선) 완료

- 사용자가 결과물의 "직선/글자 간격이 왜곡되어 곡선으로 보인다"고 지적. Shrimp Task Manager(`plan_task`→`analyze_task`→`reflect_task`→`split_tasks`)로 정식 조사·계획 수립: 실사진 3장 모두 `detect_document_corners`가 문서 경계를 전혀 검출 못 함(전체 컨투어 2200~2600개 중 가로/세로 70% 이상인 것이 0개)을 확인 — 원인은 사진이 배경 없이 화면을 프레임 가득 채운 구도(상태바가 최상단, 버튼이 최하단까지 나옴)라 "배경 대비 문서 사각형"이라는 검출 전제 자체가 성립하지 않음. 오선 하나를 픽셀 단위로 추적 측정한 결과 진짜 렌즈 곡률은 미미함(선형 피팅 잔차 최대 0.6px) — "곡선으로 보임"은 렌즈 왜곡보다 키스톤/회전 보정이 아예 적용 안 되는 것이 주원인으로 추정.
- Phase4-4의 반복 실패 전례(순수 기하 휴리스틱 재설계 2회 모두 새 회귀)를 피하기 위해 "코너 검출 알고리즘 자체를 정교화"하는 접근은 명시적으로 배제하고, Shrimp에 2개 태스크로 등록: **Task1** deskew(PRE-2) Hough 파라미터 강건성 개선(저위험), **Task2** 이미 있지만 GUI에 한 번도 연결된 적 없는 수동 코너 오버라이드(`PreprocessConfig.corners`/`DocumentCornersNotFoundError`) 배선(RT-1과 동일한 "자동+수동" 철학). 콘텐츠 기반 자동 디워핑(3단계)은 과설계 위험이 커 태스크로 만들지 않고 조건부 보류.
- **Task1 완료**: `python-dev-expert`가 `estimate_skew_angle`(`app/preprocess/deskew.py`)에 1차 시도(`threshold=100`) 실패 시 완화된 2차 시도(`threshold=50`, `minLineLength` 절반)를 추가. 재조사 결과 원래 "실패 사례"로 봤던 `IMG_2442`는 사실 실패가 아니라 1차 시도에서 이미 정확히 0도인 직선 32개를 찾아낸 정상 케이스였음이 드러남(계획 단계의 가정을 실제 재현으로 정정). `IMG_2443`은 실제로 1차 시도가 실패했었고, 2차 완화 시도로 -0.97도를 찾아내 수정됨을 확인.
- `code-reviewer`가 검토: HIGH 없음. 재시도 로직·기존 회귀·실제 문제 사진 재현 전부 정확함을 직접 재검증. MEDIUM 1건(코드 결함 아닌 서술 정정): 구현자가 트레이드오프 근거로 든 "완화된 파라미터의 노이즈 오탐률 ~1%"는 기존 단위 테스트와 같은 비현실적으로 작은 100x100 이미지에서만 측정된 수치였다 — 실제 파이프라인이 다루는 해상도(400~2400px 이상)로 올려서 재현하면 오탐률이 90~100%까지 치솟는다. 다만 이는 **이번 diff가 손대지 않은 1차 시도(threshold=100)조차 실사용 해상도에서는 이미 순수 노이즈에도 거의 항상 "성공"해버리는 Hough 접근 자체의 기존 한계**이며, 이번 2차 시도 추가가 새로 만든 위험이 아님을 별도 실측으로 확인함(실사용 해상도에서는 1차가 이미 뭔가를 찾아버려 2차가 관여할 일이 드묾). 코드 수정 없이 이 정확한 설명으로 문서화만 정정.
- 최종 검증: `tests/preprocess/ -q` → 51 passed, 1 skipped(기존과 동일한 의도된 스킵). `ruff check .` → 통과.
- 다음: Task2(수동 코너 오버라이드 GUI 연결)로 계속 진행.

## 다음 진행 방식

- 담당 에이전트: 구현은 `python-dev-expert`, 테스트는 `qa-test-engineer`, 진행상황 총괄은 `product-manager`, 커밋 전 검토는 `code-reviewer`.
- 실행 순서는 각 Phase 표의 순서를 따르되, Phase2와 Phase3는 서로 병렬 진행 가능(둘 다 Phase2-1에만 의존), Fixtures-1은 Phase1-1 직후·Phase1-2 이전에 실행.
- Task 실행: Shrimp의 `execute_task <ID>` 사용 권장 (자동으로 `verify_task`까지 유도됨).
