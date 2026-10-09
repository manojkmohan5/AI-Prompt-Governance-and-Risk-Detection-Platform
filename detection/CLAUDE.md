# CLAUDE.md (detection)

Guidance for Claude Code when working inside `detection/`. See the [root CLAUDE.md](../CLAUDE.md) for what the platform does overall and cross-cutting gotchas.

The detection service reads text for confidential content and owns the protected documents. Its one caller is the backend, which decides what to do with the answers (policy rules, the LLM call, the audit trail). Internal only: not published by Docker Compose, on a network the frontend is not on, and it never sees an end user's token.

## Commands

```bash
python -m venv venv && source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt -r requirements-ml.txt   # ML file optional — see note below

uvicorn detection.main:app --port 8002            # starts immediately; NER runs over stored documents at startup
cd detection && pytest -v
```

`requirements-ml.txt` is genuinely optional. Nothing that can block or redact a prompt uses a model — detection is regex plus dictionary lookups against the document entity index. One model does run per prompt when installed: MiniLM embeds the prompt for the advisory similarity signal. Those packages widen Knowledge Shield coverage rather than enable it: `transformers` gives NER over uploaded documents (so person and organisation names get indexed), `sentence-transformers`/`faiss-cpu` give the advisory topic-similarity signal. Without them the shield still blocks leaks using regex identifiers alone — but names of people and companies go unprotected, and the Knowledge Shield page says so. `GET /v1/status` reports which coverage is live via `ner_enabled` / `similarity_ready`.

Most tests are deliberately hermetic — NER is stubbed off and no embedding model loads, so they run offline. That is also how an NER setting that returned names as word-piece fragments ("P" + "##riya Raghavan") shipped unnoticed, so `tests/test_ml_models.py` runs the real models: it skips when the ML packages are absent, and CI runs it inside the built image against the model baked into it. Other files worth knowing: `test_service_api.py` checks what the backend gets back (the masking in `redacted_text` included) and that every route but `/health` requires `DETECTION_TOKEN` when set; `test_document_indexing.py` that a document is protected the moment it is added and unprotected when removed; `test_leak_detection.py`, `test_credentials.py` and `test_response_inspection.py` the detection itself; `test_document_upload.py` extraction from every format in `../sample_documents/`. CI also runs `python -m pyflakes detection tests conftest.py`. `test_cache.py`'s round-trip tests need a running Redis and fail without one; CI provides it. Database tests take the `db_engine` fixture from `conftest.py` (SQLite, or Postgres via `TEST_DATABASE_URL`), as in the backend.

### Docker

`Dockerfile` pre-downloads the NER and embedding checkpoints *at image build time* (see the layering comments) so a cold container needs no network and doesn't re-fetch ~260MB on first document upload; `HF_HUB_OFFLINE=1` stops any runtime download, which the internal network would refuse anyway. That RUN step sits above the code COPY so unrelated code changes don't invalidate the expensive layer. Torch is installed from `https://download.pytorch.org/whl/cpu` explicitly — the default PyPI wheel for linux/aarch64 pulls in ~1.5GB of unused NVIDIA/CUDA packages otherwise.

## Architecture

### The API (`detection/main.py`)

- `POST /v1/check/prompt` — inspection, then the Knowledge Shield (unconditionally), then risk scoring. Returns flags, score, level name, entities, every document match with the documents it came from, similarity, and `redacted_text`: PII, credentials and every document-matched span masked in place, which is what the backend sends to the LLM on a REDACT policy.
- `POST /v1/check/response` — the answer check; returns flags and the answer as it may be delivered.
- `/v1/documents` (list, add, `/batch`, `/upload`, delete) and `GET /v1/status`. Every change commits *before* rebuilding the index: the rebuild reads through its own session, which cannot see an uncommitted change. `/batch` adds many with one rebuild, because each rebuild re-runs NER over every document.
- `require_service_token` guards every `/v1` route when `DETECTION_TOKEN` is set; `/health` is open.

### Modules

1. **Inspection** (`inspector.py` + `entities.py`) — regex extracts format-defined identifiers (SSN, card w/ Luhn, email, phone, contract dates, money, reference numbers, API keys) with exact character spans, plus a phrase list for common injection openers. No model, ~1ms.
2. **Knowledge Shield** (`knowledge_shield.py`) — two signals: an exact match of prompt values against the document entity index (evidence — drives block/redact), and chunked FAISS cosine similarity (advisory — warns only, never blocks alone). Values are normalised before lookup, so reformatting an identifier doesn't evade the check. The index lives in this process's memory: one copy of the service is assumed.
3. **Risk Scoring** (`risk_scorer.py`) — flat points for what was actually found, summed, plus a co-occurrence bonus and length penalty. A conclusive document match scores 85; topic similarity alone scores 15, deliberately below the block threshold.
4. **Response Inspection** (`response_inspector.py`) — regex identifiers plus the same document entity index over the LLM's answer.
5. **Extraction** (`document_text.py`) — PDF, .docx, CSV, Markdown, text; 10MB cap. Raises `ExtractionError` with an HTTP status and a message written for the admin who picked the file; the backend passes it through.

When touching detection behavior, the regex patterns and normalisation rules live in `entities.py`; the specificity tiers that decide what counts as a confirmed leak live in `knowledge_shield.py` (`_HIGH_SPECIFICITY` / `_LOW_SPECIFICITY` / `confirm_leak`). There is no model to retrain — changing detection means changing a pattern or a tier.

### Layout

- `config.py`, `database.py`, `models.py` — this service's own settings and database (`ConfidentialDocument` only). It shares no tables with the backend.
- `encoder.py` (SentenceTransformers) and `knowledge_shield.py` import ML dependencies lazily, so the service starts without them.
- `cache.py` — optional Redis cache for the similarity search, the one per-prompt forward pass. Degrades to a no-op if Redis is unreachable. Keys embed `knowledge_shield_fingerprint()`, so a document change invalidates old entries automatically — don't key on text alone. `close_async_client()` must run before the event loop ends (the lifespan does), or the client's connections are closed after it and print "Event loop is closed".
