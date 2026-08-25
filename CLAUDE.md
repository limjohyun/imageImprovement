# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A personal (non-distributed) macOS desktop tool that turns smartphone (iPhone) photos of documents/screens (PACS scans, lecture slide photos, sheet music) into cleaned-up PDFs. Full requirements live in `docs/prd.md`; the Phase-by-Phase implementation plan (generated from the PRD via Shrimp Task Manager) lives in `docs/roadmap.md` — **read both before making architectural decisions**. `docs/roadmap.md` also tracks live progress (a per-task status column); update it when a task's status changes.

The repo is in an early scaffolding state: `app/*` subpackages exist but are still empty. Follow `docs/roadmap.md`'s task order rather than inventing new structure.

## Commands

### Environment setup (must be done in this exact order after recreating `.venv`)

Requires Python 3.12.x on PATH as `python3.12` (install via Homebrew `brew install python@3.12` or pyenv — this machine currently has neither Homebrew nor a 3.12 interpreter installed, only system Python 3.13).

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install torch==2.13.0
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python scripts/patch_basicsr.py
```

- **Python must be 3.12.x** (`requires-python = ">=3.12,<3.13"` in `pyproject.toml`). Python 3.13 breaks `basicsr` at install time because PEP 667 changed `locals()` semantics that `basicsr`'s old `exec()`-based version detection relies on — this was reproduced directly, not theoretical.
- On macOS there's no CUDA build to accidentally pull in, so `torch` installs straight from the default PyPI index (the CPU-only-index trick from the original Windows setup doesn't apply here — PyPI's macOS wheels are already CPU/MPS-only).
- `scripts/patch_basicsr.py` is required every time `.venv` is recreated: modern `torchvision` removed `torchvision.transforms.functional_tensor`, which `basicsr==1.4.2` still imports. The script is idempotent — safe to re-run.
- Dependencies in `pyproject.toml` are pinned to exact versions on purpose (this stack has already broken once from version drift). Only add a new dependency when the roadmap task that needs it starts — don't pre-install Phase2/3/5 packages (`vtracer`, `oemer`, `supabase-py`, …) early.
- External binaries (Tesseract, Ghostscript, qpdf, MuseScore — see below) install via `brew install tesseract ghostscript qpdf` / `brew install --cask musescore` when needed, gated by Phase like everything else.

### Test / lint

```bash
./.venv/bin/python -m pytest                              # all tests
./.venv/bin/python -m pytest tests/path/test_x.py::test_y  # single test
./.venv/bin/python -m ruff check .
```

GUI tests use `pytest-qt`; run headless with `QT_QPA_PLATFORM=offscreen` when there's no display.

### Shrimp Task Manager (MCP)

`.mcp.json` is git-ignored (it hardcodes a machine-local absolute path for `DATA_DIR`). Copy `.mcp.json.example` → `.mcp.json` and fill in the real path to use it; the server itself runs via `npx -y mcp-shrimp-task-manager` (published to npm), no local clone/build required. It's optional for coding/testing — only needed for regenerating/updating `docs/roadmap.md`'s task graph.

## Architecture

### Pipeline shape

All three document types (text, diagrams/charts, sheet music) share one preprocessing pipeline before branching into type-specific processors:

```
app/ingest/       → load & normalize input images
app/preprocess/    → COMMON stage, reused by every processor: perspective correction,
                      deskew, lighting normalization, Real-ESRGAN upscale
app/router/        → classifies a preprocessed image as text/diagram/score and
                      dispatches to the matching processor (introduced in Phase2 —
                      Phase1 only handles text, so no routing needed yet)
app/processors/
  text.py           → OCR (Tesseract/PaddleOCR) + OCRmyPDF → searchable PDF text layer
  diagram.py         → sharpening + optional SVG vectorization (VTracer)
  score.py            → OMR (oemer) → MusicXML → re-typeset PDF (MuseScore)
app/pdf_assembly/  → merges per-page results into one PDF; reorder/delete is Phase4
app/gui/           → PySide6 review/edit UI; heavy pipeline calls run on a QThread
                      (`ProcessingWorker`) so the UI never blocks — this is a
                      verified requirement, not just a suggestion, see roadmap Phase1-5
```

New document-type support should always reuse `app/preprocess/`, never re-implement geometry/lighting/upscale correction per type.

### External process boundaries

Several stages shell out to non-Python binaries: OCRmyPDF needs Tesseract + Ghostscript + qpdf, and score re-typesetting needs MuseScore. Always invoke these with `subprocess.run([...], shell=False)` (list args, never a shell string) — this is a hard rule, not a style preference, since these calls sit on the app's actual security boundary.

### Phased dependency & scope discipline

`docs/roadmap.md` deliberately gates both *what gets built* and *what gets installed* by Phase (1: text pipeline, 2: diagrams + routing, 3: sheet music, 4: GUI polish, 5: optional cloud backup). This is intentional, not incidental — don't jump ahead and add Phase3 (`oemer`) or Phase5 (`supabase-py`) code/dependencies while working on a Phase1 task. Phase5 (cloud backup) must stay strictly opt-in and local-save-first — the app's core loop has to work fully offline even when backup is enabled but the network is down.

### Subagents (`.claude/agents/`)

This repo defines four project-scoped subagents with distinct tool access, meant to be used rather than doing everything inline:

- `product-manager` (read-mostly) — reconciles `docs/prd.md` / `docs/roadmap.md` against actual code state, recommends next task.
- `python-dev-expert` (full write access) — implements features. Uses **snake_case/PEP 8**, not the camelCase convention from the global CLAUDE.md — that default is JS-oriented and doesn't apply here.
- `qa-test-engineer` — writes tests. GUI → `pytest-qt`; pipeline/business logic → plain `pytest`. Never Playwright/browser automation — this is a native desktop app, not a web app.
- `code-reviewer` (no write access) — reviews before commit; reports findings only.

The established flow for a roadmap task is: `python-dev-expert` implements → `code-reviewer` reviews → fixes applied → commit. Commits and code comments are in Korean per the global CLAUDE.md language rule; identifiers stay in English.
