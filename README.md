# Oatmeal Farm Network — Backend

This is the backend API for [Oatmeal Farm Network](https://oatmealfarmnetwork.com). For the full system overview and how to run frontend + backend together locally, see **[docs/SYSTEM.md](docs/SYSTEM.md)**.

## What This Repo Does

A **FastAPI** application backed by **Azure SQL** that powers the OFN platform:

- User authentication and account management (`/auth`)
- Marketplace, events, supply chain, livestock, accounting, HR, and many other domain APIs (`/api/...`)
- **[Saige](saige/README.md)** — AI agricultural advisory assistant, mounted at `/saige/*`
- **Crop Monitor proxy** — precision-ag and field data, mounted at `/cm/*` when running via `server_all.py`

The repo also contains a legacy **Node/Express** entry point (`src/index.js`) for OTF admin/nav endpoints (port 3001); most development targets the Python API.

## Prerequisites

- Python 3.11+
- Access to the OFN Azure SQL database
- For Saige features: Redis, Google Gemini credentials (see [saige/README.md](saige/README.md))
- For unified local dev with crop-monitor routes: a clone of **CropMonitoringBackend** (see [docs/SYSTEM.md](docs/SYSTEM.md))

## Setup

```powershell
# From repo root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file at the repo root. At minimum:

```env
# Database (required)
DB_SERVER=your-server.database.windows.net
DB_USER=your-user
DB_PASSWORD=your-password
DB_NAME=your-database

# Auth (required — must match Saige's SECRET_KEY)
SECRET_KEY=your-random-secret-at-least-32-chars

# App URLs
FRONTEND_URL=http://localhost:5173
OFN_BASE_URL=http://localhost:5173

# Email (password reset, notifications)
SENDGRID_API_KEY=
FROM_EMAIL=john@oatmeal-ai.com
SITE_NAME=Oatmeal Farm Network

# Payments (marketplace)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Google Cloud (translation, AI routers, biomass uploads)
GOOGLE_CLOUD_PROJECT=
GOOGLE_APPLICATION_CREDENTIALS=./path/to/service-account.json
GOOGLE_API_KEY=

# Optional
REDIS_URL=redis://localhost:6379/0
BIOMASS_GCS_BUCKET=oatmeal-farm-network-images
PLATFORM_ADMIN_IDS=1,2,3
```

For Saige-specific variables (Redis, Firestore, Gemini), create `saige/.env` — details in [saige/README.md](saige/README.md).

## Running

### Main API only

Sufficient for auth, marketplace, events, and most `/api` routes:

```powershell
python -m uvicorn main:app --reload --port 8000
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### Unified stack (main + Saige + Crop Monitor)

Requires **CropMonitoringBackend** checked out as a sibling directory (see [docs/SYSTEM.md](docs/SYSTEM.md)):

```powershell
python -m uvicorn server_all:app --reload --port 8000
```

Routes:

| Path | Service |
|------|---------|
| `/` | Main backend |
| `/saige/*` | Saige AI |
| `/cm/*` | Crop Monitor |

### Saige in isolation

```powershell
cd saige
docker compose up -d redis    # optional but recommended
uvicorn api:app --reload --port 8000
```

See [saige/README.md](saige/README.md) for API reference, graph design, and configuration.

### Legacy Node API (optional)

```powershell
node src/index.js
```

Runs on port 3001. Used by the frontend for `VITE_OTF_API_URL` nav-config endpoints.

## Tests

Saige has pytest coverage:

```powershell
cd saige
pytest
```

Integration tests (`test_api_flow.py`, `test_redis.py`) require running Redis and valid `.env` credentials.

## Scripts & Utilities

| Path | Purpose |
|------|---------|
| `scripts/` | Database seed scripts |
| `seed_*.py` | Domain-specific seed data |
| `scrapers/` | Knowledge-base scrapers (e.g. Lavendir) |
| `saige/seed_firestore.py` | Seed RAG knowledge into Firestore |
| `saige/sync_embeddings.py` | Refresh Firestore vector embeddings |
| `saige/deploy.ps1` | Deploy Saige to Cloud Run |

## Deployment

The root `Dockerfile` builds the main FastAPI app:

```dockerfile
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
```

Saige has its own `saige/Dockerfile.backend` and `saige/deploy.ps1` for standalone Cloud Run deployment. Production runs separate Cloud Run services for main, Saige, and Crop Monitor — see [docs/SYSTEM.md](docs/SYSTEM.md).

## Project Layout

```
oatmealfarmnetworkbackend/
├── main.py              # FastAPI app entry point
├── server_all.py        # Unified launcher (main + Saige + Crop Monitor)
├── database.py          # SQLAlchemy / pymssql connection
├── auth.py              # JWT helpers
├── routers/             # API route modules
├── models.py            # SQLAlchemy models
├── saige/               # AI advisory subsystem
├── src/index.js         # Legacy Node API
├── requirements.txt
├── docs/
│   └── SYSTEM.md        # Cross-repo architecture (source of truth)
└── README.md            # This file
```

## Related Documentation

- **[docs/SYSTEM.md](docs/SYSTEM.md)** — architecture, local full-stack setup, ports, production overview
- **[saige/README.md](saige/README.md)** — Saige API, LangGraph design, RAG, Redis, env reference
- **[Frontend README](https://github.com/Oatmeal-Farm-Network/oatmealfarmnetwork/blob/main/README.md)** — React app setup and `VITE_*` variables
