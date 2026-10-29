# ThreadNest AI Support Agent

> AI-powered customer support for ThreadNest — India's favourite online clothing store.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Client (Browser / App)                │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend (:8000)                    │
│                                                              │
│  /auth  ──► JWT Auth (customer & staff)                      │
│  /chat  ──► ChatEndpoint ──► LangGraph Agent                 │
│                              │                               │
│                    ┌─────────▼──────────┐                    │
│                    │   LangGraph Graph  │                    │
│                    │  classify_intent   │                    │
│                    │  load_context      │                    │
│                    │  agent_step (loop) │                    │
│                    │  format_response   │                    │
│                    └─────────┬──────────┘                    │
│                              │ Tool Calls                    │
│          ┌───────────────────▼───────────────────┐           │
│          │              Tool Registry             │           │
│          │  order_tools  │ refund_tools           │           │
│          │  policy_tools │ replacement_tools      │           │
│          │  ticket_tools │ ...                    │           │
│          └───────────────────┬───────────────────┘           │
│                              │                               │
│  /approvals ──► Staff review queue                           │
│  /admin     ──► Metrics & analytics                          │
└──────────────────────────────┼──────────────────────────────┘
                               │ asyncpg / SQLAlchemy
┌──────────────────────────────▼──────────────────────────────┐
│            PostgreSQL 16 + pgvector (:5432)                  │
│  customers · orders · refunds · tickets · conversations      │
│  messages · tool_calls · approvals · policy_chunks           │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+ (for local dev)
- An OpenAI API key

### Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd ai_support_agent

# 2. Create your .env file
cp backend/.env.example .env
# Edit .env and set your OPENAI_API_KEY and JWT_SECRET

# 3. Start the database (and backend)
docker compose up -d

# 4. (Optional) Seed the database with test data
cd backend
pip install -e ".[dev]"
python -m seed.seed

# 5. Visit the API docs
open http://localhost:8000/docs
```

### Local Development (without Docker for backend)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start just the DB via Docker
docker compose up -d db

# Run the backend locally
uvicorn app.main:app --reload --port 8000
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/login` | None | Customer login → JWT |
| `POST` | `/auth/staff/login` | None | Staff login → JWT |
| `GET` | `/health` | None | Health check |
| `POST` | `/chat` | Customer JWT | Send a message to the AI agent |
| `WS` | `/chat/ws/{conversation_id}` | None | WebSocket streaming (v2) |
| `GET` | `/approvals` | Staff JWT | List pending approvals |
| `GET` | `/approvals/{id}` | Staff JWT | Get single approval |
| `POST` | `/approvals/{id}/decide` | Staff JWT | Approve or reject |
| `GET` | `/admin/metrics` | Staff JWT | System metrics |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `OPENAI_API_KEY` | `sk-placeholder` | OpenAI API key |
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `JWT_EXPIRY_HOURS` | `24` | Token validity in hours |
| `REFUND_AUTO_APPROVE_LIMIT` | `1000.0` | Auto-approve refunds ≤ this amount (INR) |
| `AGENT_MAX_STEPS` | `6` | Max LangGraph agent steps per turn |
| `MODEL_NAME` | `gpt-4o` | OpenAI model to use |
| `ENVIRONMENT` | `development` | `development` or `production` |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI 0.115+ |
| LLM Orchestration | LangGraph 0.2+ |
| LLM | OpenAI GPT-4o |
| Database | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.0 (async) |
| Auth | JWT (python-jose) + bcrypt |
| Validation | Pydantic v2 |
| Containerisation | Docker + Docker Compose |
| Testing | pytest + pytest-asyncio |

---

## Project Milestones

| Week | Milestone | Status |
|------|-----------|--------|
| 1 | Backend scaffold: FastAPI, DB schema, LangGraph agent skeleton, tool stubs, JWT auth | ✅ Done |
| 2 | Full tool implementations + approval workflow + seed data testing | 🔄 Planned |
| 3 | Policy RAG with pgvector embeddings | 🔄 Planned |
| 4 | Evaluation harness + golden dataset | 🔄 Planned |
| 5 | Staff dashboard (Next.js) | 🔄 Planned |
| 6 | WebSocket streaming responses | 🔄 Planned |
| 7 | Observability: tracing, cost tracking, latency dashboards | 🔄 Planned |
| 8 | Production hardening: rate limiting, secrets management, load testing | 🔄 Planned |

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

## Linting

```bash
cd backend
ruff check app/ seed/ tests/
```
