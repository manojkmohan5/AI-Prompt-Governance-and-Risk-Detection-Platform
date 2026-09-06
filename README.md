# AI Prompt Governance & Risk Detection Platform

> Enterprise AI governance middleware — intercepts, inspects, scores, and enforces policy on every LLM prompt before it reaches the model.

---

## What It Does

Every prompt an employee submits passes through a **9-stage governance pipeline** before reaching the LLM.

The core job is keeping confidential document content out of the LLM. Each uploaded document is indexed into its constituent entities — identifiers by regex, names by NER — and every prompt is checked against that index. A hit means a value that literally exists in a protected file was typed into the prompt: evidence, not a guess. That is what drives blocking and redaction.

Semantic similarity is kept as a second, deliberately weaker signal. It only ever says "this prompt is about the same subject as a protected document", which is true of plenty of harmless prompts, so on its own it warns and never blocks.

Nothing on the per-prompt path runs a model. Detection is regex and dict lookups (~1ms); NER runs only at document upload.

```
User ──► Frontend (React/Vite :5173)
              │
              ▼
         FastAPI Gateway  /api/v1  (:8001)
              │
    ┌─────────┴──────────────────────┐
    │        Governance Pipeline      │
    │                                 │
    │  1. Inspection                  │  Regex entities + injection phrases
    │  2. Knowledge Shield            │  Doc entity index (exact)
    │                                 │  + chunked FAISS (advisory)
    │  3. Risk Scoring                │  Evidence-based points, 0–100
    │  4. Anomaly Detection           │  Z-score per-user baseline
    │  5. Compliance Mapping          │  GDPR · HIPAA · SOC2 · EU AI Act
    │  6. Policy Enforcement          │  ALLOW / WARN / REDACT / BLOCK
    └─────────┬──────────────────────┘
              │  (if not BLOCKED)
              ▼
         Groq LLM  (llama-3.3-70b-versatile)
              │
    ┌─────────┴──────────────────────┐
    │     Response Inspection         │  Entity index on LLM output;
    │                                 │  leaked spans masked, not just flagged
    └─────────┬──────────────────────┘
              ▼
         Audit Log + Analytics Dashboard
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Recharts |
| Backend | FastAPI, Python 3.12, Uvicorn |
| Database | SQLite (via SQLAlchemy 2.0 async) |
| Entity extraction | Regex (identifiers, Luhn-checked cards) + NER (`dslim/distilbert-NER`, upload-time only) |
| Embeddings | SentenceTransformers (`all-MiniLM-L6-v2`) |
| Vector Search | FAISS (`faiss-cpu`) |
| LLM Provider | Groq API (`llama-3.3-70b-versatile`) |
| Auth | JWT (python-jose + bcrypt) |
| Cache | Redis (optional — classifier + Knowledge Shield results) |
| Deployment | Docker + Docker Compose (backend, frontend/nginx, Redis) |

---

## Project Structure

```
Mini Enquino/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/    # auth, prompts, analytics, policies, audit, knowledge-shield
│   │   ├── core/                # config, database, security
│   │   ├── governance/          # entities, inspector, risk_scorer, response_inspector
│   │   ├── embeddings/          # encoder, knowledge_shield (FAISS)
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   └── services/            # prompt_service, analytics_service, llm_service, anomaly_service
│   ├── seed_data/seed.py        # Demo users, prompt history, policy rules, protected docs
│   ├── tests/                   # pytest suite (app/core/cache.py)
│   ├── main.py                  # FastAPI app entry point
│   ├── Dockerfile               # Pre-downloads NER + embedding checkpoints into the image
│   ├── requirements.txt         # Core dependencies
│   └── requirements-ml.txt      # PyTorch + Transformers + FAISS (not fully optional — see backend/CLAUDE.md)
├── frontend/
│   ├── src/
│   │   ├── pages/               # Login, Dashboard, PromptConsole, AuditLogs, Analytics...
│   │   ├── components/          # RiskBadge, MetricCard
│   │   ├── context/             # AuthContext (JWT)
│   │   ├── services/api.ts      # Axios API client
│   │   ├── layouts/             # DashboardLayout (sidebar nav)
│   │   └── types/               # TypeScript interfaces
│   ├── Dockerfile               # Multi-stage build -> nginx
│   └── nginx.conf               # Serves the SPA, proxies /api to the backend
├── .github/workflows/ci.yml     # Backend + frontend checks, Docker build + smoke test
├── docker-compose.yml           # Full stack: backend + frontend + Redis
├── .env.example                 # Environment variable template
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node 20+
- A free [Groq API key](https://console.groq.com)

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# Install dependencies (core + ML)
pip install -r requirements.txt
pip install -r requirements-ml.txt

# Configure environment
cp ../.env.example .env
# Edit .env — set GROQ_API_KEY to your key

# Run the API  (starts immediately; nothing is trained at boot)
uvicorn main:app --host 0.0.0.0 --port 8001

# In a second terminal — seed demo data
python -m seed_data.seed
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# App: http://localhost:5173
```

### Docker (alternative to the above)

```bash
docker compose up --build
# Frontend: http://localhost   Backend: http://localhost:8001
```

Runs backend + frontend (nginx) + Redis together. The backend image pre-downloads the NER and embedding checkpoints at *build* time, so a cold container doesn't re-fetch ~260MB on first document upload. Set `GROQ_API_KEY` (and optionally `SECRET_KEY`) in a `.env` file at the repo root before running — `docker-compose.yml` reads it via variable substitution.

---

## Demo Accounts

| Name | Email | Password | Role | Department |
|------|-------|----------|------|------------|
| Admin | admin@acme.corp | Admin@1234 | Admin | Security |
| James Wong | james.wong@acme.corp | User@1234 | Employee | Engineering |
| Lisa Park | lisa.park@acme.corp | User@1234 | Employee | Sales |
| Mark Chen | mark.chen@acme.corp | User@1234 | Employee | Finance |

Admin unlocks: Audit Logs, Analytics, Policy Rules, Knowledge Base.

---

## Detection Categories

Every signal below is evidence — a regex match, an index hit, or a matched phrase — so there is no confidence score to threshold.

### Confidential document leaks

Uploaded documents are indexed into entities. A prompt is checked against that index, and values are normalised first, so reformatting an identifier (`492 83 7291` for `492-83-7291`) does not evade the check.

| Signal | Flag | Base Risk | When it fires |
|--------|------|-----------|---------------|
| Identifier from a document | `CONFIDENTIAL_DOC_LEAK` | 85 | SSN, card, email, phone, reference number matched |
| Name from a document | `CONFIDENTIAL_DOC_LEAK` | 70 | PERSON matched (NER-indexed at upload) |
| Two weak values, same document | `CONFIDENTIAL_DOC_LEAK` | 60 | e.g. a date *and* a salary from one file |
| Topic similarity only | `KNOWLEDGE_SHIELD_SIMILAR` | 15 | Advisory. Never blocks alone |

One shared date or dollar figure is coincidence, so it warns rather than blocks; two values from the same file is not, so it does. That split is what keeps unrelated prompts from being stopped.

### Prompt and response content

| Signal | Flag | Base Risk | Example |
|--------|------|-----------|---------|
| PII (SSN, card, passport, IBAN) | `PII_DETECTED` | 50 | `492-83-7291` |
| PII (email, phone) | `PII_DETECTED` | 30 | `dana@corp.com` |
| Credentials | `SENSITIVE_DATA` | 45 | `sk-…`, `AKIA…`, bearer tokens |
| Injection phrase | `PROMPT_INJECTION` | 80 | "Ignore all previous instructions" |
| Leak in the LLM's reply | `RESPONSE_DOC_LEAK` / `RESPONSE_PII_LEAK` / `RESPONSE_SECRET_LEAK` | — | Masked before it reaches the caller |

Co-occurrence of 2+ signals adds a bonus (+8 or +15). Redaction masks the matched span only, so `"Dana's SSN is 492-83-7291 and the invoice was $4,000"` keeps the invoice figure.

**Not detected:** toxicity, and injection phrased as a paraphrase rather than one of the listed openers. A word list is trivially evaded and false-positives on ordinary words, so it was left out rather than faked. If either matters, a hosted moderation endpoint is the right addition — the `openai` package is already a dependency.

Risk levels: `LOW` (<30) · `MEDIUM` (30–59) · `HIGH` (60–79) · `CRITICAL` (≥80)

---

## API Reference

Base URL: `http://localhost:8001/api/v1`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/login` | — | Login → JWT token |
| POST | `/prompts` | Employee | Submit prompt through governance pipeline |
| GET | `/prompts` | Employee | List own prompt history |
| GET | `/analytics/overview` | Admin | Dashboard metrics |
| GET | `/policies` | Admin | List policy rules |
| POST | `/policies` | Admin | Create policy rule |
| PATCH | `/policies/{id}/toggle` | Admin | Enable/disable rule |
| GET | `/knowledge-shield/documents` | Admin | List protected docs |
| POST | `/knowledge-shield/documents` | Admin | Add doc to shield |
| GET | `/audit` | Admin | Audit log explorer |

Interactive docs: `http://localhost:8001/docs`

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | SQLite path (default: `sqlite+aiosqlite:///./governance.db`) |
| `SECRET_KEY` | JWT signing secret — change in production |
| `GROQ_API_KEY` | Required — get free key at [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | Default: `llama-3.3-70b-versatile` |
| `RISK_BLOCK_THRESHOLD` | Score above which BLOCK applies (default: 80) |
| `RISK_WARN_THRESHOLD` | Score above which WARN applies (default: 50) |
| `KNOWLEDGE_SHIELD_THRESHOLD` | Cosine similarity trigger (default: 0.75) |
| `EMBEDDING_MODEL` | SentenceTransformers model (default: `all-MiniLM-L6-v2`) |
| `REDIS_URL` | Optional cache for the classifier + Knowledge Shield (default: `redis://localhost:6379/0`); both degrade to running uncached if unreachable |
| `CACHE_ENABLED` | Set `false` to disable the Redis cache outright (default: `true`) |
| `CACHE_TTL_SECONDS` | Cache entry lifetime (default: 604800 / 7 days) |

---

## Future Improvements

- [ ] PostgreSQL migration for multi-tenant production scale
- [ ] Real-time WebSocket event stream
- [ ] Alembic database migrations
- [ ] CSV / PDF compliance report export
- [ ] Slack / PagerDuty alerting on CRITICAL events
- [ ] Rate limiting per user and department
