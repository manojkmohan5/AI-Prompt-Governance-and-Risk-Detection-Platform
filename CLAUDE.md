# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Enterprise AI governance middleware: intercepts every LLM prompt, runs it through an 8-stage ML governance pipeline (PII, prompt injection, sensitive data, toxicity, IP leak, high-risk ML request detection — via a fine-tuned DistilBERT classifier, zero regex), scores risk, enforces policy (ALLOW/WARN/REDACT/BLOCK), and forwards allowed prompts to Groq's LLM API. Full write-up of the pipeline, tech stack, and API surface is in [README.md](README.md) — read it for the architecture diagram and detection-category thresholds table.

This is a two-package repo: `backend/` (FastAPI + SQLAlchemy + the ML governance pipeline) and `frontend/` (React/Vite dashboard). Each has its own `CLAUDE.md` with commands and architecture specific to that package — [backend/CLAUDE.md](backend/CLAUDE.md) and [frontend/CLAUDE.md](frontend/CLAUDE.md) — loaded automatically when working in those directories. This root file only covers things that span both.

## Cross-cutting notes

- **No automated tests anywhere in this repo** — no pytest config/test files in `backend/`, no test runner configured in `frontend/`. `npm run build` (`tsc -b`) is the only automated check on the frontend side.
- **Known port mismatch**: `frontend/vite.config.ts` proxies `/api` to `http://localhost:8000`, but the README and the documented `uvicorn` command both use port `8001`. Check which port the backend is actually running on before assuming the proxy works — align one or the other rather than guessing.
- **Accessibility**: all web UI code (`frontend/src`) must meet WCAG 2.1 AA. See [frontend/CLAUDE.md](frontend/CLAUDE.md) for specifics.
