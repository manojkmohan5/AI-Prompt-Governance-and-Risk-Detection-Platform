# AI Prompt Governance & Risk Detection Platform

> Enterprise AI governance middleware — intercepts, inspects, scores, and enforces policy on every LLM prompt before it reaches the model.

---

## What It Does

Every prompt an employee submits passes through an **8-stage ML governance pipeline** before reaching the LLM. The platform detects PII, prompt injection, sensitive data, toxicity, IP leaks, and high-risk ML requests — all using a fine-tuned DistilBERT classifier (zero regex).

```
User ──► Frontend (React/Vite :5173)
              │
              ▼
         FastAPI Gateway  /api/v1  (:8001)
              │
    ┌─────────┴──────────────────────┐
    │        Governance Pipeline      │
    │                                 │
    │  1. ML Inspection               │  Fine-tuned DistilBERT (6 categories)
    │  2. Risk Scoring                │  Confidence-weighted, 0–100
    │  3. Knowledge Shield            │  FAISS semantic search
    │  4. Anomaly Detection           │  Z-score per-user baseline
    │  5. Compliance Mapping          │  GDPR · HIPAA · SOC2 · EU AI Act
    │  6. Policy Enforcement          │  ALLOW / WARN / REDACT / BLOCK
    └─────────┬──────────────────────┘
              │  (if not BLOCKED)
              ▼
         Groq LLM  (llama-3.3-70b-versatile)
              │
    ┌─────────┴──────────────────────┐
    │     Response Inspection         │  DistilBERT on LLM output
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
| ML Classifier | DistilBERT (`distilbert-base-uncased`, fine-tuned, 66M params) |
| Embeddings | SentenceTransformers (`all-MiniLM-L6-v2`) |
| Vector Search | FAISS (`faiss-cpu`) |
| LLM Provider | Groq API (`llama-3.3-70b-versatile`) |
| Auth | JWT (python-jose + bcrypt) |

---

## Project Structure

```
Mini Enquino/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/    # auth, prompts, analytics, policies, audit, knowledge-shield
│   │   ├── core/                # config, database, security
│   │   ├── governance/          # ml_classifier, inspector, risk_scorer, response_inspector
│   │   ├── embeddings/          # encoder, knowledge_shield (FAISS)
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   └── services/            # prompt_service, analytics_service, llm_service, anomaly_service
│   ├── seed_data/seed.py        # Demo users, prompt history, policy rules, protected docs
│   ├── main.py                  # FastAPI app entry point
│   ├── requirements.txt         # Core dependencies
│   └── requirements-ml.txt      # PyTorch + Transformers + FAISS
├── frontend/
│   └── src/
│       ├── pages/               # Login, Dashboard, PromptConsole, AuditLogs, Analytics...
│       ├── components/          # RiskBadge, MetricCard
│       ├── context/             # AuthContext (JWT)
│       ├── services/api.ts      # Axios API client
│       ├── layouts/             # DashboardLayout (sidebar nav)
│       └── types/               # TypeScript interfaces
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

# Run the API  (DistilBERT trains on first run ~3 min, cached after)
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

## ML Detection Categories

The fine-tuned DistilBERT classifier runs a single forward pass and outputs confidence scores for all 6 categories simultaneously (multi-label).

| Category | Flag | Threshold | Base Risk Score | Example Trigger |
|----------|------|-----------|-----------------|-----------------|
| PII_DATA | `PII_DETECTED` | 0.38 | 50 | SSN, credit card, email |
| PROMPT_INJECTION | `PROMPT_INJECTION` | 0.36 | 80 | "Ignore all previous instructions" |
| SENSITIVE_DATA | `SENSITIVE_DATA` | 0.38 | 45 | "Q4 pricing strategy", API keys |
| TOXICITY | `TOXICITY` | 0.40 | 75 | Ransomware, harmful content |
| IP_LEAK | `IP_LEAK` | 0.36 | 40 | Model weights, training data extraction |
| ML_HIGH_RISK | `ML_HIGH_RISK` | 0.34 | 70 | Scrape PII, bypass audit logs |

Risk score = `base × min(confidence / 0.55, 1.0)`. Co-occurrence of 2+ categories adds a bonus (+8 or +15).

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

---

## Future Improvements

- [ ] PostgreSQL migration for multi-tenant production scale
- [ ] Real-time WebSocket event stream
- [ ] Alembic database migrations
- [ ] CSV / PDF compliance report export
- [ ] Slack / PagerDuty alerting on CRITICAL events
- [ ] Rate limiting per user and department
- [ ] Docker deployment configuration
