# imageImprovement

스마트폰 촬영 이미지(PACS 화면/PPT/악보 등)를 인식·보정해서 고화질 PDF로 만드는 개인용 Python 도구.

요구사항은 `docs/prd.md`, 개발 로드맵은 `docs/roadmap.md` 참고.

## 개발 환경

- Python **3.12.x** 필수 (3.13 이상 미지원 — 아래 "알려진 이슈" 참고)

### venv 활성화

```powershell
.\.venv\Scripts\Activate.ps1
```

### 테스트 실행

```powershell
.\.venv\Scripts\python.exe -m pytest
```

### 린트

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

## 설치 (venv 재생성 시 아래 순서 그대로)

```powershell
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe scripts\patch_basicsr.py
```

torch를 먼저 CPU 전용 인덱스(`https://download.pytorch.org/whl/cpu`)에서 설치하는 이유: PyPI 기본 인덱스에는 `torch==2.13.0+cpu` 같은 로컬 버전(CPU 빌드)이 없고, 순서를 지키지 않으면 이후 `pip install -e ".[dev]"` 단계에서 torch가 기본 인덱스의 (용량이 훨씬 큰) CUDA 빌드로 다시 설치될 수 있다.

## 알려진 이슈 / venv 재생성 시 필요한 작업

### 1. Python 버전은 반드시 3.12

Python 3.13은 PEP 667(`locals()` 동작 변경)로 인해 `basicsr`(Real-ESRGAN 의존성) 설치 자체가 깨지는 것을 실제로 재현 확인했다(3.14 이상은 미검증). `pyproject.toml`의 `requires-python`도 `>=3.12,<3.13`으로 제한되어 있다.

### 2. basicsr 패치 (venv 재생성 시 반드시 다시 적용)

최신 torchvision(0.17+)에서 `torchvision.transforms.functional_tensor` 모듈이 삭제되어, `basicsr==1.4.2`의 `basicsr/data/degradations.py`가 import 시점에 아래와 같은 에러로 깨진다.

```
ModuleNotFoundError: No module named 'torchvision.transforms.functional_tensor'
```

`.venv`를 새로 만든 뒤(즉 `basicsr`를 재설치한 뒤) 아래 스크립트를 한 번 실행해 패치를 다시 적용한다.

```powershell
.\.venv\Scripts\python.exe scripts\patch_basicsr.py
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

## Shrimp Task Manager MCP 연결 (선택, 로드맵 관리용)

`.mcp.json`은 머신별 절대경로(mcp-shrimp-task-manager 클론 위치)를 담고 있어 git에 커밋하지 않는다(`.gitignore` 처리). 처음 설정할 때:

```powershell
cp .mcp.json.example .mcp.json
```

복사한 `.mcp.json`에서 `<mcp-shrimp-task-manager 클론 경로>`를 실제로 `mcp-shrimp-task-manager`를 clone+build한 경로로, `<이 저장소 절대경로>`를 이 저장소의 절대경로로 바꿔라. 이 파일이 없으면 Claude Code에서 `docs/roadmap.md`를 만든 Shrimp Task Manager 도구들을 쓸 수 없을 뿐, 나머지 개발(코드 작성/테스트)에는 영향 없다.

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
