# CLAUDE.md (backend)

Guidance for Claude Code when working inside `backend/`. See the [root CLAUDE.md](../CLAUDE.md) for what the platform does overall and cross-cutting gotchas.

## Commands

```bash
python -m venv venv && source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
cp ../.env.example .env                              # then set GROQ_API_KEY

uvicorn main:app --host 0.0.0.0 --port 8001          # run API (starts immediately)
python -m seed_data.seed                             # seed demo users, policies, prompt history, protected docs
```

The backend has no ML dependencies: everything that reads text for content runs in the detection service (`../detection`), which must be running for prompts to be processed and for seeding. The seeder sends the demo documents to it in one batch; it indexes them on arrival, so no restart is needed.

```bash
cd backend && pytest -v      # needs ../detection/requirements.txt installed in the same environment
```
Files worth knowing: `test_detection_unavailable.py` checks the platform fails closed — a prompt that cannot be checked is refused and never reaches the LLM, an answer that cannot be checked is withheld, and logins and history keep working; `test_seed.py` runs the real detection app in-process (via `httpx.ASGITransport`) so the seeded history comes from the real checks and never calls the LLM; `test_admin_only.py` checks every Knowledge Shield route refuses employees before anything reaches the detection service; `test_access_control.py` that prompt records are private to their owner and only admins create accounts; `test_policy_validation.py` that bad rules are refused and an unloadable one is removed at startup; `test_policy_migration.py` that old databases are repaired on startup; and `test_security_hardening.py` the unsafe-by-default fixes. CI also runs `python -m pyflakes app main.py tests seed_data conftest.py`.

Tests that need a database take the `db_engine` fixture from `conftest.py` rather than creating an engine: a fresh SQLite file per test, or — with `TEST_DATABASE_URL` set, as CI's second run does — a real Postgres, emptied first. Postgres enforces foreign keys and `VARCHAR` lengths and refuses `0`/`1` for booleans, none of which SQLite does, so raw SQL uses `TRUE`/`FALSE`, test rows that reference a user need the user inserted first, and new string columns need a matching `max_length` on the input schema.

### Docker

`docker-compose.yml` (repo root) runs the full stack — `docker compose up --build`. `backend/Dockerfile` is a plain Python image with no models; the heavy image is the detection service's.

## Architecture

### Governance pipeline (the core of the system)

`app/services/prompt_service.py::process()` is the orchestrator every prompt flows through, in this exact order:

1. **Detection** (`app/services/detection_client.py` → detection service `POST /v1/check/prompt`) — inspection (regex identifiers with exact spans, injection phrases), the Knowledge Shield (document entity index + advisory similarity) and the risk score, in one call. Returns flags, score, level, entities, document matches, similarity and `redacted_text`. See [detection/CLAUDE.md](../detection/CLAUDE.md) for how each part works.
2. **Anomaly Detection** (`app/services/anomaly_service.py`) — per-user Z-score against their rolling risk baseline (needs ≥5 prior prompts); `USER_ANOMALY` flag adds +10 risk.
3. **Compliance Mapping** (`app/governance/compliance_mapper.py`) — static flag → {GDPR, HIPAA, SOC2, EU AI Act, ISO 42001, NIST AI RMF} lookup table, purely for audit evidence tagging.
4. **Policy Enforcement** (`app/governance/policy_engine.py`) — loads active `PolicyRule` rows ordered by priority, evaluates each rule's condition (`risk_score_above` / `flag_contains` / `department_is` / `always`), and takes the *strictest* matching action (ALLOW < WARN < REDACT < BLOCK).
5. **LLM Call** (`app/services/llm_service.py`) — skipped if the action is BLOCK. If REDACT, the detection service's `redacted_text` is sent instead: PII, credentials and every value traced to a protected document masked in place, so the surrounding question stays usable. Falls back to a mock response string if `GROQ_API_KEY` is unset.
6. **Answer check** (detection service `POST /v1/check/response`) — a document can leak in the answer to a prompt that contained nothing. Leaked spans are masked before the response reaches the caller, not merely flagged.
7. **Persist** — writes `PromptRecord`, `AuditLog`, and one `RiskEvent` per severity-mapped flag, all in the same DB transaction.

Steps 1 and 6 **fail closed**: `detection_client` raises `DetectionUnavailable` for an unreachable service, a timeout (`DETECTION_TIMEOUT_SECONDS`) or any error status, and `main.py`'s exception handler turns it into a 503. The transaction rolls back, so nothing is persisted. A 401/403 from detection (a `DETECTION_TOKEN` mismatch) is treated the same way — passed through as a 401 it would sign the employee out.

### Protected documents

`app/api/v1/endpoints/knowledge_shield.py` is a thin admin-only layer: every route takes `require_admin`, then forwards to the detection service, which owns the documents, extracts uploaded files and re-indexes. The detection service never sees an end user's token, so these routes are the only guard. The detection service's own refusals (`DetectionRefused`: a scanned PDF, a legacy `.doc`, a missing document) are passed through with their status and message, which are written for the admin. Uploads are capped at 10MB here as well, reading at most one byte past the limit, so an oversized file is refused before it is buffered and forwarded.

### Layout

- `app/api/v1/endpoints/` — one router module per resource (auth, prompts, analytics, policies, audit, knowledge_shield), wired together in `app/api/v1/router.py`.
- `app/api/deps.py` — JWT bearer auth; `get_current_user` and `require_admin` are the two dependencies gating routes. Roles are just `admin` / `employee` (`app/models/user.py`).
- `app/services/detection_client.py` — the only code that talks to the detection service. A new connection per call; `_transport` lets tests route calls to an in-process app or an `httpx.MockTransport`.
- `app/core/database.py` — async SQLAlchemy 2.0. Postgres via `asyncpg` in Docker, SQLite via `aiosqlite` when run directly; code must work on both. No Alembic: schema changes are applied via a manual `_NEW_COLUMNS` / `ALTER TABLE` migration list in `main.py`'s `_migrate()`, run on every startup. Add new nullable columns there rather than introducing a migration framework.
- `main.py` — startup runs non-destructive migrations: `_migrate` adds columns, `_migrate_policy_rules` repairs rules in databases seeded before the classifier was removed (rekeys the old `KNOWLEDGE_SHIELD` flag to `CONFIDENTIAL_DOC_LEAK`, retires rules on flags nothing raises). Seeding skips an existing database (except for sending documents to an empty detection service), so this is the only thing that updates one.
- Settings (`app/core/config.py`) are `pydantic-settings`-driven from `.env`. Blocking and warning thresholds are policy rules in the database, not settings. `GROQ_API_KEY` must be empty for the mock LLM — any non-empty value is sent to Groq as a real key. `DETECTION_URL` / `DETECTION_TOKEN` / `DETECTION_TIMEOUT_SECONDS` point at the detection service. A `SECRET_KEY` starting with `change-this` (every placeholder in the repo does) is swapped for a random per-process key by `ensure_secret_key`, so tokens are never signed with a published key; `DEBUG` (default off) controls whether errors return stack traces.
