# Saige — AI Agricultural Advisory Assistant

A conversational AI system that provides farm-specific advice across livestock, crops, weather, and mixed topics. Built with LangGraph, FastAPI, and Google Gemini AI, backed by Firestore RAG and Redis for short-term memory.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Graph & Node Design](#graph--node-design)
- [RAG Collections](#rag-collections)
- [Chat History & Message Buffer](#chat-history--message-buffer)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Prerequisites & Installation](#prerequisites--installation)
- [Running the Application](#running-the-application)
- [Technologies Used](#technologies-used)
- [Security Notes](#security-notes)

---

## Overview

Saige guides farmers through a structured diagnostic conversation:

1. **Assessment** — open-ended questions build a farm context (location, crops/animals, issues)
2. **Routing** — hybrid keyword + LLM classifier picks the right advisory node
3. **Advisory** — the selected node generates advice, optionally augmented by RAG knowledge and live weather data

Supported advisory domains:
- **Livestock** — breed recommendations, health, husbandry (RAG: `rag_livestock`)
- **Crops / Plants** — disease, soil, agronomy (RAG: `rag_plant`)
- **Weather** — current conditions and forecasts via Open-Meteo
- **Bakasura** — product/service knowledge base (RAG: `rag_bakasura`)
- **News** — agricultural news and market updates (RAG: `rag_news`)
- **Mixed** — any query spanning multiple domains (uses all RAG collections)

---

## Architecture

```
Frontend (Next.js/React)
        │
        ▼
FastAPI REST API  (api.py)
        │
        ├── Redis  ── short-term message buffer (last N messages)
        │              rate limiter (per-thread INCR/EXPIRE)
        │              LangGraph checkpoints (RedisSaver)
        │
        ├── Firestore ── chat history persistence (chat-history DB)
        │                RAG knowledge collections (charlie DB)
        │
        └── LangGraph Workflow  (graph.py)
                │
                ├── assessment_node
                ├── routing_node
                ├── weather_advisory_node
                ├── livestock_advisory_node
                ├── crop_advisory_node
                ├── mixed_advisory_node
                ├── bakasura_advisory_node
                └── news_advisory_node
                        │
                        └── Google Gemini AI  (llm.py)
```

---

## Project Structure

```
saige/
├── api.py                  # FastAPI app, endpoints, rate limiting, middleware
├── graph.py                # LangGraph StateGraph construction and compilation
├── nodes.py                # All node functions, routing logic, advisory engine
├── models.py               # FarmState TypedDict and Pydantic models
├── config.py               # Centralized env-var configuration and feature flags
├── llm.py                  # Google Gemini LLM initialization
├── rag.py                  # Firestore vector search (livestock, plant, bakasura, news)
├── chat_history.py         # Firestore-backed conversation persistence
├── message_buffer.py       # Redis short-term message buffer (last N messages)
├── jwt_auth.py             # JWT Bearer token verification (FastAPI dependency)
├── redis_client.py         # RedisClientManager (connection pooling, health checks)
├── weather.py              # Open-Meteo weather service and LangChain tool wrapper
├── database.py             # Azure SQL (pymssql) query helpers
├── Data_Contract.py        # Pydantic data contracts for external integrations
├── main.py                 # Application entry point / server startup
├── sync_embeddings.py      # Script to sync embeddings into Firestore RAG collections
├── seed_firestore.py       # Script to seed initial knowledge data into Firestore
├── test_api_flow.py        # Integration tests for the full API flow
├── test_main.py            # Unit tests for core logic
└── test_redis.py           # Redis connectivity and buffer tests
```

---

## Graph & Node Design

### State: `FarmState`

| Field | Type | Purpose |
|---|---|---|
| `location` | `str` | Farmer's location (used for weather queries) |
| `farm_size` | `str` | Farm area |
| `crops` | `List[str]` | Crops or animals being raised |
| `current_issues` | `List[str]` | Reported problems or goals |
| `history` | `List[str]` | Conversation turns (`"User: ..."`, `"AI: ..."`) |
| `assessment_summary` | `str` | Compact summary produced at assessment completion |
| `advisory_type` | `str` | Final routed type: `weather`/`livestock`/`crops`/`mixed` |
| `diagnosis` | `str` | Final advisory text |
| `recommendations` | `List[str]` | Structured recommendations |
| `weather_conditions` | `dict` | Fetched weather data |
| `soil_info` | `dict` | Parsed soil test metrics |

### Graph Flow

```
START → assessment_node ──(complete?)──▶ routing_node
             ▲                                │
             │ (more questions)               ▼
             └──────────────────── weather / livestock / crop /
                                   mixed / bakasura / news → END
```

- `assessment_node` uses LLM-structured output (`AssessmentDecision`) to decide whether to ask another question or mark the assessment complete. It respects `MAX_QUESTIONS = 8`.
- `routing_node` classifies the `assessment_summary` using keyword scoring + LLM fallback (`QueryClassification`) to select one of six advisory routes.
- Each advisory node fetches relevant RAG context and/or weather data, then generates a final response via Gemini.

---

## RAG Collections

All RAG retrieval uses Firestore vector search with `text-embedding-004` embeddings (top-K = 10).

| Collection constant | Firestore collection | Used by |
|---|---|---|
| `LIVESTOCK_KNOWLEDGE_COLLECTION` | `livestock_knowledge` | `livestock_advisory_node` |
| `PLANT_KNOWLEDGE_COLLECTION` | `plant_knowledge` | `crop_advisory_node` |
| `BAKASURA_DOCS_COLLECTION` | `bakasura-docs` | `bakasura_advisory_node` |
| `NEWS_ARTICLES_COLLECTION` | `news_articles` | `news_advisory_node` |

`mixed_advisory_node` queries **all three** advisory collections (`livestock_knowledge`, `plant_knowledge`, `bakasura-docs`).

RAG is enabled only when `FIRESTORE_AVAILABLE` and the full RAG dependency stack (pymssql, VertexAI embeddings) is installed. Both degrade gracefully when unavailable.

---

## Chat History & Message Buffer

### Firestore Chat History (`chat_history.py`)

Persists every conversation to the `chat-history` Firestore database under:

```
threads/{thread_id}               ← thread metadata (user_id, status, preview, …)
  └── messages/{message_id}       ← individual messages (role, content, ts, metadata)
```

Key operations:
- `save_message()` — upserts thread doc, writes message subcollection entry
- `mark_complete()` — sets `status: complete`, records `advisory_type` and `farm_context`
- `get_threads()` / `get_messages()` — paginated reads (cursor-based)
- `get_analytics()` — aggregate stats (completion rate, type distribution, response latency)
- `delete_thread()` — batch-deletes messages then the thread doc

### Redis Message Buffer (`message_buffer.py`)

Keeps the last `SHORT_TERM_N` (default 20) messages per thread in Redis for fast in-context history injection. TTL defaults to 24 hours (`SHORT_TERM_TTL_SECONDS`).

Key format: `thread:{thread_id}:last_messages`

---

## API Reference

Base URL: `http://localhost:8000`

### Authentication

All non-health endpoints require a valid JWT in the `Authorization` header:

```
Authorization: Bearer <token>
```

Tokens are issued by the Oatmeal Farm Network auth backend and verified against `SECRET_KEY` using HS256. The `sub` claim is used as the `user_id`. A missing, expired, or invalid token returns `401`.

### `POST /chat`

Main advisory endpoint. Requires JWT.

**Request:**
```json
{
  "user_input": "my cattle have been losing weight",
  "thread_id": "thread_abc123"
}
```

**Response — assessment question:**
```json
{
  "status": "requires_input",
  "ui": {
    "type": "quiz",
    "question": "What type of cattle are you raising?",
    "options": ["Beef cattle", "Dairy cattle", "Mixed herd", "Not sure"]
  }
}
```

**Response — advisory complete:**
```json
{
  "status": "complete",
  "advice": "Based on the symptoms described, your cattle may be experiencing …",
  "advisory_type": "livestock"
}
```

**Rate limiting:** 20 requests per 60-second window per `thread_id` (Redis-backed, fail-open).

### `GET /`

Health check. Returns API version and feature list.

### `GET /health`

Shallow liveness probe.

### `GET /health/redis`

Redis connectivity check. Returns latency and connection mode.
- `200 disabled` — Redis off by config
- `200 healthy` — reachable
- `503 unhealthy` — enabled but unreachable

### `GET /health/firestore`

Deep Firestore health check (write/read/delete cycle).

### `GET /ready`

Readiness probe. Checks graph, Redis, and Firestore. Returns `503` if any critical service is down.

### `GET /threads` *(if enabled)*

List conversation threads for the authenticated user (paginated). Requires JWT.

### `GET /threads/{thread_id}/messages` *(if enabled)*

Fetch messages for a thread (paginated). Requires JWT.

### `DELETE /threads/{thread_id}` *(if enabled)*

Delete a thread and all its messages. Requires JWT.

### `GET /analytics` *(if enabled)*

Aggregate conversation stats for the authenticated user. Requires JWT.

---

## Configuration

### Environment Variables

Create a `.env` file in the `saige/` directory (or project root):

```env
# --- Authentication ---
SECRET_KEY=your_jwt_secret_key               # HS256 signing secret (required)

# --- GCP / Gemini ---
GOOGLE_API_KEY=your_gemini_api_key           # Developer API (simplest)
GEMINI_MODEL=gemini-2.5-flash-lite

# --- OR Vertex AI ---
GOOGLE_CLOUD_PROJECT=your-gcp-project
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=./credentials/service-account.json

# --- Firestore ---
FIRESTORE_DATABASE=charlie                   # RAG knowledge database
CHAT_HISTORY_DATABASE=chat-history           # Conversation persistence database

# --- Redis ---
REDIS_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=                              # Leave blank for no auth
REDIS_DB=0
REDIS_SSL=false
# Or use a full URL (takes precedence):
# REDIS_URL=redis://localhost:6379/0

# --- Azure SQL (optional, for database.py) ---
DB_HOST=
DB_PORT=1433
DB_USER=
DB_PASSWORD=
DB_NAME=

# --- API ---
FRONTEND_URL=http://localhost:3000
ALLOW_ALL_ORIGINS=false

# --- Safety controls ---
MAX_MESSAGE_CHARS=4000
MAX_STORED_CONTENT_CHARS=2000
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX_REQUESTS=20
RATE_LIMIT_WINDOW_SECONDS=60

# --- Tuning ---
SHORT_TERM_N=20                              # Last N messages kept in Redis buffer
SHORT_TERM_TTL_SECONDS=86400                 # 24h default
SYNC_INTERVAL_HOURS=24
```

### Full Variable Reference

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | HS256 JWT signing secret (required for all protected endpoints) |
| `GOOGLE_API_KEY` | — | Gemini Developer API key |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | LLM model (Developer API) |
| `GOOGLE_CLOUD_PROJECT` | — | GCP project (Vertex AI) |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | GCP region |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Service account JSON path |
| `FIRESTORE_DATABASE` | `charlie` | RAG knowledge Firestore DB |
| `CHAT_HISTORY_DATABASE` | `chat-history` | Chat persistence Firestore DB |
| `REDIS_ENABLED` | `true` | Enable/disable Redis entirely |
| `REDIS_URL` | — | Full Redis URL (overrides host/port) |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | — | Redis auth password |
| `REDIS_SSL` | `false` | Enable TLS for Redis |
| `REDIS_SSL_CERT_REQS` | `required` | TLS cert policy (`required`/`optional`/`none`) |
| `SHORT_TERM_N` | `20` | Messages kept in Redis buffer per thread |
| `SHORT_TERM_TTL_SECONDS` | `86400` | Buffer TTL in seconds |
| `MAX_MESSAGE_CHARS` | `4000` | Max chars per user message |
| `RATE_LIMIT_MAX_REQUESTS` | `20` | Rate limit — max requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit — window size in seconds |
| `FRONTEND_URL` | `http://localhost:3000` | Allowed CORS origin |
| `ALLOW_ALL_ORIGINS` | `false` | Allow all CORS origins |

---

## Prerequisites & Installation

### Prerequisites

- Python 3.11+
- Redis 7+ (or GCP Memorystore)
- Google Cloud project with Firestore and Vertex AI enabled (for RAG)
- Node.js 18+ (for the frontend)

### Backend Setup

```bash
# From the repo root
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy and fill in your env vars
cp .env.example .env
```

### Frontend Setup

```bash
cd frontend
npm install
```

---

## Running the Application

### Backend

```bash
# From the saige/ directory
uvicorn api:app --reload --port 8000
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm run dev
```

Frontend available at `http://localhost:3000`.

### Utility Scripts

```bash
# Seed initial knowledge data into Firestore
python seed_firestore.py

# Sync/refresh embeddings in RAG collections
python sync_embeddings.py
```

---

## Technologies Used

| Layer | Technology |
|---|---|
| LLM | Google Gemini 2.5 Flash Lite (via `langchain-google-genai` or Vertex AI) |
| Orchestration | LangGraph (StateGraph, interrupts, checkpointing) |
| API | FastAPI 0.100+ / Uvicorn |
| Vector search | Firestore vector search + `text-embedding-004` |
| Short-term memory | Redis (message buffer + LangGraph RedisSaver checkpoints) |
| Long-term persistence | Google Cloud Firestore |
| Weather data | Open-Meteo (via `requests`) |
| Database | Azure SQL / pymssql |
| Authentication | `python-jose` (JWT HS256 Bearer tokens) |
| Validation | Pydantic v2 |
| Frontend | Next.js, React 19, TypeScript, Tailwind CSS |

---

## Security Notes

**Never commit:**
- `.env` files (API keys, database credentials)
- `credentials/` directory (GCP service account JSON files)
- Any file containing secrets or tokens

The `.gitignore` excludes `.env`, `credentials/`, virtual environments, `__pycache__`, and `node_modules`.

**Production checklist:**
- Set a strong, randomly generated `SECRET_KEY` (minimum 32 characters)
- Set `ALLOW_ALL_ORIGINS=false` and configure `FRONTEND_URL` explicitly
- Enable `REDIS_SSL=true` with `REDIS_SSL_CERT_REQS=required` when using managed Redis
- Rotate API keys, JWT secrets, and service account credentials periodically
- Review `git status` before pushing to confirm no secrets are staged

---

## Troubleshooting

| Error | Solution |
|---|---|
| `401 Invalid or expired token` | Ensure a valid JWT is sent in the `Authorization: Bearer <token>` header |
| `500 JWT_SECRET is not configured` | Set `SECRET_KEY` in your `.env` file |
| `GOOGLE_API_KEY not set` | Create `.env` with `GOOGLE_API_KEY=...` |
| `RAG disabled (requires Firestore)` | Install `google-cloud-firestore` and set `GOOGLE_CLOUD_PROJECT` |
| `Redis checkpoint indexes missing` | API falls back to `MemorySaver` automatically; restart Redis and re-run |
| `401 UNAUTHENTICATED` | Verify API key or service account credentials file path |
| CORS errors | Ensure backend is on port 8000 and `FRONTEND_URL` matches |
| `No such index` in Redis logs | Redis checkpoint index not initialized; the fallback handler in `api.py` covers this automatically |
