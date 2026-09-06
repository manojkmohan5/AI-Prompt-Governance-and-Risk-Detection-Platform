# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Enterprise AI governance middleware: intercepts every LLM prompt, runs it through a 9-stage governance pipeline, scores risk, enforces policy (ALLOW/WARN/REDACT/BLOCK), and forwards allowed prompts to Groq's LLM API. The core job is stopping confidential document content from reaching the LLM: uploaded documents are indexed into their constituent entities (regex identifiers + NER names), and every prompt is matched against that index. Detection on the per-prompt path is regex and dict lookups — no model. Full write-up of the pipeline, tech stack, and API surface is in [README.md](README.md) — read it for the architecture diagram and detection-category thresholds table.

This is a two-package repo: `backend/` (FastAPI + SQLAlchemy + the ML governance pipeline) and `frontend/` (React/Vite dashboard). Each has its own `CLAUDE.md` with commands and architecture specific to that package — [backend/CLAUDE.md](backend/CLAUDE.md) and [frontend/CLAUDE.md](frontend/CLAUDE.md) — loaded automatically when working in those directories. This root file only covers things that span both.

## Cross-cutting notes

- **Testing**: `backend/tests/` has a small pytest suite (currently covering `app/core/cache.py`); no frontend test runner exists — `npm run build` (`tsc -b`) is the only automated check on that side. CI (`.github/workflows/ci.yml`) runs both, plus a Docker build + smoke test job.
- **Docker**: `docker-compose.yml` at the repo root runs the full stack (backend, frontend via nginx, Redis) — `docker compose up --build`. The backend image pre-downloads the NER and embedding checkpoints in the build layer (see `backend/Dockerfile`) so a cold container doesn't re-fetch them on first document upload. See [backend/CLAUDE.md](backend/CLAUDE.md) for details on that layering and why torch is installed from the CPU-only index.
- **Accessibility**: all web UI code (`frontend/src`) must meet WCAG 2.1 AA. See [frontend/CLAUDE.md](frontend/CLAUDE.md) for specifics.
