# CLAUDE.md (backend)

Guidance for Claude Code when working inside `backend/`. See the [root CLAUDE.md](../CLAUDE.md) for what the platform does overall and cross-cutting gotchas.

## Commands

```bash
python -m venv venv && source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt                     # core deps
pip install -r requirements-ml.txt                   # optional: needed for Knowledge Shield (FAISS + embeddings)
cp ../.env.example .env                              # then set GROQ_API_KEY

uvicorn main:app --host 0.0.0.0 --port 8001          # run API (fine-tunes DistilBERT on first run, ~3 min on CPU; cached after in app/governance/_bert_finetuned/)
python -m seed_data.seed                             # seed demo users, policies, prompt history, protected docs
```

There is no test suite in this repo (no pytest config, no test files) and no linter config for the backend.

## Architecture

### Governance pipeline (the core of the system)

`app/services/prompt_service.py::process()` is the orchestrator every prompt flows through, in this exact order:

1. **ML Inspection** (`app/governance/inspector.py` + `ml_classifier.py`) — single DistilBERT forward pass returns sigmoid confidence per category; scores above per-category thresholds become governance flags. Zero regex anywhere in detection.
2. **Risk Scoring** (`risk_scorer.py`) — `score = base_points × min(confidence/norm, 1.0)` per flagged category, summed, plus a co-occurrence bonus for 2+ simultaneous flags and a length penalty. Maps to LOW/MEDIUM/HIGH/CRITICAL.
3. **Knowledge Shield** (`app/embeddings/knowledge_shield.py`) — only runs if risk_score ≥ 20; FAISS cosine similarity against confidential document embeddings (SentenceTransformers). A match adds the `KNOWLEDGE_SHIELD` flag and +20 risk.
4. **Anomaly Detection** (`app/services/anomaly_service.py`) — per-user Z-score against their rolling risk baseline (needs ≥5 prior prompts); `USER_ANOMALY` flag adds +10 risk.
5. **Compliance Mapping** (`app/governance/compliance_mapper.py`) — static flag → {GDPR, HIPAA, SOC2, EU AI Act, ISO 42001, NIST AI RMF} lookup table, purely for audit evidence tagging.
6. **Policy Enforcement** (`app/governance/policy_engine.py`) — loads active `PolicyRule` rows ordered by priority, evaluates each rule's condition (`risk_score_above` / `flag_contains` / `department_is` / `always`), and takes the *strictest* matching action (ALLOW < WARN < REDACT < BLOCK).
7. **LLM Call** (`app/services/llm_service.py`) — skipped if the action is BLOCK. If REDACT, the prompt is passed through ML-based sentence-level redaction (`ml_classifier.redact_entities`) before being sent to Groq (OpenAI-compatible client). Falls back to a mock response string if `GROQ_API_KEY` is unset.
8. **Response Inspection** (`app/governance/response_inspector.py`) — re-runs the same DistilBERT classifier over chunked LLM output with *higher* thresholds than prompt inspection (so explanatory/educational responses about security topics don't false-positive), looking for leaked secrets, unsafe content, or injection artifacts in the model's own reply.
9. **Persist** — writes `PromptRecord`, `AuditLog`, and one `RiskEvent` per severity-mapped flag, all in the same DB transaction.

When touching detection behavior, the fine-tuning corpus and per-category thresholds live together in `app/governance/ml_classifier.py` — retraining requires deleting `app/governance/_bert_finetuned/` so `initialize()` re-fine-tunes on next startup.

### Layout

- `app/api/v1/endpoints/` — one router module per resource (auth, prompts, analytics, policies, audit, knowledge_shield), wired together in `app/api/v1/router.py`.
- `app/api/deps.py` — JWT bearer auth; `get_current_user` and `require_admin` are the two dependencies gating routes. Roles are just `admin` / `employee` (`app/models/user.py`).
- `app/core/database.py` — async SQLAlchemy 2.0, SQLite via `aiosqlite`. No Alembic: schema changes are applied via a manual `_NEW_COLUMNS` / `ALTER TABLE` migration list in `main.py`'s `_migrate()`, run on every startup. Add new nullable columns there rather than introducing a migration framework.
- `app/embeddings/` — `encoder.py` (SentenceTransformers) and `knowledge_shield.py` (FAISS) both import ML dependencies lazily and degrade gracefully (Knowledge Shield goes to "standby"/inactive) if `requirements-ml.txt` isn't installed.
- Settings (`app/core/config.py`) are `pydantic-settings`-driven from `.env`; note `KNOWLEDGE_SHIELD_THRESHOLD` defaults differ between `config.py` (0.55) and `.env.example` (0.75) — the `.env` value wins once present.
- `app/core/cache.py` — optional Redis cache for the two transformer forward passes (classifier `classify()`, Knowledge Shield `check_similarity()`). Degrades to a no-op if Redis is unreachable, same pattern as the ML deps. Cache keys embed a fingerprint of the model/index (`classifier_fingerprint()` / `knowledge_shield_fingerprint()`) so a retrain or a Knowledge Shield document change invalidates old entries automatically — don't key on text alone.
