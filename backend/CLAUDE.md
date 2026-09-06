# CLAUDE.md (backend)

Guidance for Claude Code when working inside `backend/`. See the [root CLAUDE.md](../CLAUDE.md) for what the platform does overall and cross-cutting gotchas.

## Commands

```bash
python -m venv venv && source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt -r requirements-ml.txt   # both required — see note below
cp ../.env.example .env                              # then set GROQ_API_KEY

uvicorn main:app --host 0.0.0.0 --port 8001          # run API (starts immediately; nothing is trained at boot)
python -m seed_data.seed                             # seed demo users, policies, prompt history, protected docs
```

`requirements-ml.txt` is genuinely optional. No model runs on the per-prompt path — detection is regex plus dict lookups against the document entity index. Those packages widen Knowledge Shield coverage rather than enable it: `transformers` gives NER over uploaded documents (so person and organisation names get indexed), `sentence-transformers`/`faiss-cpu` give the advisory topic-similarity signal. Without them the shield still blocks leaks using regex identifiers alone. `GET /api/v1/knowledge-shield/status` reports which coverage is live via `ner_enabled` / `similarity_ready`.

```bash
cd backend && pytest -v   # tests/ covers app/core/cache.py and leak detection
```
`tests/test_leak_detection.py` is deliberately hermetic — NER is stubbed off and no embedding model loads, so it runs offline and exercises the regex-only degraded path.
No linter is configured for the backend.

### Docker

`docker-compose.yml` (repo root) runs backend + frontend + Redis together — `docker compose up --build`. `backend/Dockerfile` pre-downloads the NER and embedding checkpoints *at image build time* (see the layering comments in the Dockerfile) so a cold container doesn't re-fetch ~260MB on first document upload. That RUN step sits above the app COPY so unrelated code changes don't invalidate the expensive layer. Torch is installed from `https://download.pytorch.org/whl/cpu` explicitly — the default PyPI wheel for linux/aarch64 pulls in ~1.5GB of unused NVIDIA/CUDA packages otherwise.

## Architecture

### Governance pipeline (the core of the system)

`app/services/prompt_service.py::process()` is the orchestrator every prompt flows through, in this exact order:

1. **Inspection** (`app/governance/inspector.py` + `entities.py`) — regex extracts format-defined identifiers (SSN, card w/ Luhn, email, phone, contract dates, money, reference numbers, API keys) with exact character spans, plus a phrase list for common injection openers. No model, ~1ms.
2. **Knowledge Shield** (`app/embeddings/knowledge_shield.py`) — runs *unconditionally*. Two signals: an exact match of prompt values against the document entity index (evidence — drives block/redact), and chunked FAISS cosine similarity (advisory — warns only, never blocks alone). Values are normalised before lookup, so reformatting an identifier doesn't evade the check.
3. **Risk Scoring** (`risk_scorer.py`) — flat points for what was actually found, summed, plus a co-occurrence bonus and length penalty. A conclusive document match scores 85; topic similarity alone scores 15, deliberately below the block threshold.
4. **Anomaly Detection** (`app/services/anomaly_service.py`) — per-user Z-score against their rolling risk baseline (needs ≥5 prior prompts); `USER_ANOMALY` flag adds +10 risk.
5. **Compliance Mapping** (`app/governance/compliance_mapper.py`) — static flag → {GDPR, HIPAA, SOC2, EU AI Act, ISO 42001, NIST AI RMF} lookup table, purely for audit evidence tagging.
6. **Policy Enforcement** (`app/governance/policy_engine.py`) — loads active `PolicyRule` rows ordered by priority, evaluates each rule's condition (`risk_score_above` / `flag_contains` / `department_is` / `always`), and takes the *strictest* matching action (ALLOW < WARN < REDACT < BLOCK).
7. **LLM Call** (`app/services/llm_service.py`) — skipped if the action is BLOCK. If REDACT, PII spans and any value traced to a protected document are masked *in place* (`entities.redact`) before the prompt goes to Groq, so the surrounding question stays usable. Falls back to a mock response string if `GROQ_API_KEY` is unset.
8. **Response Inspection** (`app/governance/response_inspector.py`) — regex identifiers plus the same document entity index over the LLM's reply, because a document can leak in the answer to a prompt that contained nothing. Leaked spans are masked before the response reaches the caller, not merely flagged.
9. **Persist** — writes `PromptRecord`, `AuditLog`, and one `RiskEvent` per severity-mapped flag, all in the same DB transaction.

### Adding protected documents

Two ways in, one code path. `POST /knowledge-shield/documents` takes pasted
JSON; `POST /knowledge-shield/documents/upload` takes a file (PDF, .docx, CSV,
Markdown, text — 10MB cap). Both are **admin only**, like every route on that
router: `require_admin` is a dependency on each one, so an employee can neither
add to nor read the protected set.

Extraction lives in `app/services/document_text.py`, deliberately outside the
endpoint module — it is pure parsing with no auth, DB or FastAPI dependency, so
it can be tested without importing the auth stack. It raises `ExtractionError`
carrying an HTTP status and a message written for the admin who picked the
file; the endpoint just re-raises it as an `HTTPException`.

Fixtures for every supported format live in `sample_documents/` and are what
`tests/test_document_upload.py` runs against, so regenerating them badly fails
the suite rather than silently weakening detection.

When touching detection behavior, the regex patterns and normalisation rules live in `app/governance/entities.py`; the specificity tiers that decide what counts as a confirmed leak live in `app/embeddings/knowledge_shield.py` (`_HIGH_SPECIFICITY` / `_LOW_SPECIFICITY` / `confirm_leak`). There is no model to retrain — changing detection means changing a pattern or a tier.

### Layout

- `app/api/v1/endpoints/` — one router module per resource (auth, prompts, analytics, policies, audit, knowledge_shield), wired together in `app/api/v1/router.py`.
- `app/api/deps.py` — JWT bearer auth; `get_current_user` and `require_admin` are the two dependencies gating routes. Roles are just `admin` / `employee` (`app/models/user.py`).
- `app/core/database.py` — async SQLAlchemy 2.0, SQLite via `aiosqlite`. No Alembic: schema changes are applied via a manual `_NEW_COLUMNS` / `ALTER TABLE` migration list in `main.py`'s `_migrate()`, run on every startup. Add new nullable columns there rather than introducing a migration framework.
- `app/embeddings/` — `encoder.py` (SentenceTransformers) and `knowledge_shield.py` (FAISS) both import ML dependencies lazily and degrade gracefully (Knowledge Shield goes to "standby"/inactive) if `requirements-ml.txt` isn't installed.
- Settings (`app/core/config.py`) are `pydantic-settings`-driven from `.env`; note `KNOWLEDGE_SHIELD_THRESHOLD` defaults differ between `config.py` (0.55) and `.env.example` (0.75) — the `.env` value wins once present.
- `app/core/cache.py` — optional Redis cache for the two transformer forward passes (classifier `classify()`, Knowledge Shield `check_similarity()`). Degrades to a no-op if Redis is unreachable, same pattern as the ML deps. Cache keys embed a fingerprint of the model/index (`classifier_fingerprint()` / `knowledge_shield_fingerprint()`) so a retrain or a Knowledge Shield document change invalidates old entries automatically — don't key on text alone.
