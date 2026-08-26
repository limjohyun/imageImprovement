# imageImprovement

스마트폰 촬영 이미지(PACS 화면/PPT/악보 등)를 인식·보정해서 고화질 PDF로 만드는 개인용 Python 도구.

요구사항은 `docs/prd.md`, 개발 로드맵은 `docs/roadmap.md` 참고.

## 개발 환경

- OS: macOS
- Python **3.12.x** 필수 (3.13 이상 미지원 — 아래 "알려진 이슈" 참고). Homebrew(`brew install python@3.12`) 또는 pyenv로 설치.

### venv 생성/활성화

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 테스트 실행

```bash
.venv/bin/python -m pytest
```

### 린트

```bash
.venv/bin/python -m ruff check .
```

## 설치 (venv 재생성 시 아래 순서 그대로)

```bash
.venv/bin/python -m pip install torch==2.13.0
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python scripts/patch_basicsr.py
.venv/bin/python scripts/install_oemer.py
```

macOS에는 CUDA 빌드 자체가 없어서(Windows/Linux처럼 별도 CPU 전용 인덱스를 지정할 필요 없이) 기본 PyPI 인덱스에서 설치해도 자동으로 CPU/MPS 전용 빌드가 설치된다.

## 알려진 이슈 / venv 재생성 시 필요한 작업

### 1. Python 버전은 반드시 3.12

Python 3.13은 PEP 667(`locals()` 동작 변경)로 인해 `basicsr`(Real-ESRGAN 의존성) 설치 자체가 깨지는 것을 실제로 재현 확인했다(3.14 이상은 미검증). `pyproject.toml`의 `requires-python`도 `>=3.12,<3.13`으로 제한되어 있다.

### 2. basicsr 패치 (venv 재생성 시 반드시 다시 적용)

최신 torchvision(0.17+)에서 `torchvision.transforms.functional_tensor` 모듈이 삭제되어, `basicsr==1.4.2`의 `basicsr/data/degradations.py`가 import 시점에 아래와 같은 에러로 깨진다.

```
ModuleNotFoundError: No module named 'torchvision.transforms.functional_tensor'
```

`.venv`를 새로 만든 뒤(즉 `basicsr`를 재설치한 뒤) 아래 스크립트를 한 번 실행해 패치를 다시 적용한다.

```bash
.venv/bin/python scripts/patch_basicsr.py
```

이 스크립트는 `basicsr/data/degradations.py`의

```python
from torchvision.transforms.functional_tensor import rgb_to_grayscale
```

를

```python
from torchvision.transforms.functional import rgb_to_grayscale
```

로 치환한다(이미 패치되어 있으면 아무것도 하지 않음).

### 3. oemer(Phase3 OMR) 설치 (venv 재생성 시 반드시 다시 적용)

`oemer==0.1.8`은 PyPI 메타데이터상 `onnxruntime-gpu`를 하드 의존성으로 선언하는데, 이 패키지는 macOS(Darwin)용 배포판이 PyPI에 전혀 없어 `pip install oemer`를 그대로 실행하면 다음과 같이 실패한다(실제 재현 확인함).

```
ERROR: No matching distribution found for onnxruntime-gpu
```

oemer 코드 자체는 `import onnxruntime`만 하고 GPU 전용 API를 강제하지 않으므로, CPU 전용 `onnxruntime`을 먼저 정상 설치해두고(이는 `pyproject.toml`의 일반 dependencies가 책임진다) `oemer` 자체는 `--no-deps`로 설치해 문제되는 의존성 해석을 건너뛴다. 이 때문에 `pyproject.toml`에 `oemer`를 일반 dependencies로 그냥 추가할 수 없다(`pip install -e ".[dev]"`가 oemer의 선언된 메타데이터를 그대로 resolve하려다 다시 실패한다).

`.venv`를 새로 만든 뒤(즉 `pip install -e ".[dev]"`로 onnxruntime 등 정상 의존성을 설치한 뒤) 아래 스크립트를 한 번 실행한다.

```bash
.venv/bin/python scripts/install_oemer.py
```

이 스크립트는 `oemer==0.1.8`을 `--no-deps`로 설치한다(이미 설치되어 있으면 아무것도 하지 않음). `opencv-python-headless`(oemer가 원래 요구하는 패키지)는 설치하지 않는다 — 이 프로젝트가 이미 쓰는 `opencv-python`과 같은 `cv2` 네임스페이스를 공유해 충돌하기 때문이다(`--no-deps`로 자동으로 건너뛴다).

OMR 체크포인트(`.onnx`/`.h5`, 수백MB)는 oemer 최초 실행 시 [BreezeWhite/oemer GitHub Releases](https://github.com/BreezeWhite/oemer/releases)에서 자동 다운로드된다. 체크포인트가 없는 상태에서 `app.processors.score.recognize_score()`를 호출하면 `ScoreModelUnavailableError`가 발생하며, 관련 테스트는 이 경우 자동으로 skip된다.

## Shrimp Task Manager MCP 연결 (선택, 로드맵 관리용)

`.mcp.json`은 머신별 절대경로(`DATA_DIR`)를 담고 있어 git에 커밋하지 않는다(`.gitignore` 처리). 처음 설정할 때:

```bash
cp .mcp.json.example .mcp.json
```

복사한 `.mcp.json`에서 `<이 저장소 절대경로>`를 이 저장소의 절대경로로 바꿔라. 서버 자체는 npm에 배포된 `mcp-shrimp-task-manager`를 `npx -y mcp-shrimp-task-manager`로 실행하므로 별도 clone/build가 필요 없다. 이 파일이 없으면 Claude Code에서 `docs/roadmap.md`를 만든 Shrimp Task Manager 도구들을 쓸 수 없을 뿐, 나머지 개발(코드 작성/테스트)에는 영향 없다.

## 모듈 구조

```
app/
  ingest/        # 이미지 입력, 포맷 정규화
  preprocess/    # 원근보정, deskew, 조명보정, 업스케일 (공통, 모든 processor가 재사용)
  router/        # 문서 유형 분류 → processor 라우팅
  processors/    # text.py / diagram.py / score.py
  pdf_assembly/  # 여러 페이지를 하나의 PDF로 조립
  gui/           # PySide6 기반 편집/검수 UI
tests/           # pytest 테스트
scripts/         # 개발 편의 스크립트 (basicsr 패치 등)
```
