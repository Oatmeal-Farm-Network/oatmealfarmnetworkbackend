# Oatmeal Farm Network — Backend

FastAPI backend for the Oatmeal Farm Network platform: agricultural management, marketplace, events, auth, and the Saige AI advisory service (`saige/`).

**Repo:** [Oatmeal-Farm-Network/oatmealfarmnetworkbackend](https://github.com/Oatmeal-Farm-Network/oatmealfarmnetworkbackend)

---

## Table of contents

- [Overview](#overview)
- [Repository layout](#repository-layout)
- [Quick start (local)](#quick-start-local)
- [Configuration](#configuration)
- [Staging & CI/CD](#staging--cicd)
- [Database (staging)](#database-staging)
- [Documentation index](#documentation-index)
- [API overview](#api-overview)
- [Technologies](#technologies)
- [Development](#development)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## Overview

Enterprise-scale FastAPI app with **100+ routers** across farm operations domains, plus an optional AI advisory stack in `saige/`.

| Area | Examples |
|------|----------|
| Auth & users | JWT auth, profiles, subscriptions |
| Crops & fields | Precision ag, soil tests, irrigation, scouting, yields |
| Livestock | Herd health, meat, ranches |
| Harvest & cold chain | Produce, grain bins, perishable trace |
| Marketplace | Catalog, equipment, Stripe |
| Supply chain | Routing, procurement, provenance |
| Events | Auctions, fairs, registration, check-in |
| Finance | Cash flow, budgets, settlements |
| Content | Website builder, blog, news |
| AI | Saige (LangGraph + Gemini) — separate service in staging |

---

## Repository layout

Package code lives under **`app/`** (not a top-level `routers/` folder):

```text
.
├── app/
│   ├── main.py              # FastAPI app (staging Cloud Run entry: app.main:app)
│   ├── database.py          # SQLAlchemy / pymssql / Cloud SQL Connector
│   ├── dependencies.py      # Shared FastAPI deps
│   ├── schema_ensure.py     # Optional lazy DDL (skipped on RO staging)
│   ├── models.py
│   ├── core/                # JWT / shared auth helpers
│   └── routers/             # Domain API routers
├── saige/                   # AI advisory (own Dockerfile + CD)
│   ├── api.py               # Shim → app/api.py (uvicorn api:app)
│   ├── app/ graph/ chat/ core/ tools/ agents/ …
│   ├── integrations/ workers/ data/ services/ schemas/
│   ├── Dockerfile.backend
│   └── README.md
├── oatsense/                # Precision-ag BFF + CropMonitor proxy (own Dockerfile + CD)
│   ├── api.py               # uvicorn oatsense.api:app
│   ├── Dockerfile.backend
│   └── cloudbuild.yaml
├── otf/                     # Over the Fence Social (livestock-style thin service + CD)
│   ├── api.py               # uvicorn otf.api:app → mounts app.routers.mill
│   ├── Dockerfile.backend
│   └── cloudbuild.yaml
├── livestock/               # Livestock microservice (own Dockerfile + CD)
├── test/                    # Unit / smoke tests
├── docs/                    # Staging, IAM, Cloud Run runbooks
├── scripts/                 # One-off maintenance scripts
├── server_all.py            # Local/unified: main + Saige in one process
├── Dockerfile               # Default CMD = server_all (overridden on staging backend)
├── requirements.txt
└── .github/workflows/
    ├── deploy-staging.yml            # Main backend → oatmeal-backend-staging
    ├── deploy-saige.yml              # Saige → oatmeal-saige-staging
    ├── deploy-oatsense-staging.yml   # Oatsense → oatmeal-oatsense-staging
    ├── deploy-oatsense-prod.yml      # Oatsense → oatmeal-oatsense
    ├── deploy-otf-staging.yml        # OTF → oatmeal-otf-staging
    ├── deploy-livestock-staging.yml
    └── ci.yml
```

**Imports in Docker / Cloud Run** use the `app.` package prefix, e.g. `from app.database import get_db`, `from app.dependencies import get_current_user`.

---

## Quick start (local)

### Prerequisites

- Python 3.11+
- SQL Server reachable via `DB_*` (or Cloud SQL Auth Proxy locally)
- Optional: Redis + Google credentials for Saige

### Install

```bash
git clone https://github.com/Oatmeal-Farm-Network/oatmealfarmnetworkbackend.git
cd oatmealfarmnetworkbackend

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # if present — otherwise create .env (see Configuration)
```

### Run main API only

```bash
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs`.

### Run Saige only

```bash
cd saige
uvicorn api:app --reload --port 8001
```

See [`saige/README.md`](saige/README.md).

### Run unified (main + Saige)

```bash
uvicorn server_all:app --reload --port 8000
```

Requires Saige LLM auth (`GOOGLE_API_KEY` or `GOOGLE_CLOUD_PROJECT`).  
**Staging backend does not use `server_all`** — Saige is deployed separately.

---

## Configuration

Root `.env` (typical):

```env
SECRET_KEY=your_jwt_secret

# SQL Server (local / Auth Proxy)
DB_SERVER=127.0.0.1
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database

# Cloud Run staging sets these instead of relying on localhost proxy:
# INSTANCE_CONNECTION_NAME=project:region:instance
# SKIP_SCHEMA_ENSURE=true

# Saige (optional locally)
GOOGLE_API_KEY=
# or GOOGLE_CLOUD_PROJECT=... + GOOGLE_GENAI_USE_VERTEXAI=true
FRONTEND_URL=http://localhost:3000
```

| Variable | Role |
|----------|------|
| `DB_*` | SQL login (always needed for DB access) |
| `INSTANCE_CONNECTION_NAME` | If set, `app/database.py` uses **Cloud SQL Python Connector** + `pytds` (Cloud Run staging) |
| `SKIP_SCHEMA_ENSURE` | Skip lazy DDL helpers (required for read-only staging DB) |
| `SECRET_KEY` | JWT signing |

---

## Staging & CI/CD

GCP project: **`oatmeal-farm-staging`** · Region: **`us-central1`**

| Pipeline | Branch | Workflow | Cloud Run service |
|----------|--------|----------|-------------------|
| Main backend | `GCP/backend-staging` | `.github/workflows/deploy-staging.yml` | `oatmeal-backend-staging` |
| Saige | `GCP/saige-staging` | `.github/workflows/deploy-saige.yml` | `oatmeal-saige-staging` |
| Oatsense | `GCP/backend-staging` (path-filtered) | `.github/workflows/deploy-oatsense-staging.yml` | `oatmeal-oatsense-staging` |
| Oatsense prod | `GCP/oatsense-prod` / `oatsense-v*` / dispatch | `.github/workflows/deploy-oatsense-prod.yml` | `oatmeal-oatsense` |
| OTF Social | `GCP/backend-staging` (path-filtered) | `.github/workflows/deploy-otf-staging.yml` | `oatmeal-otf-staging` |

→ Oatsense runbook: [`docs/oatsense-deploy.md`](docs/oatsense-deploy.md)  
→ OTF runbook: [`docs/otf-deploy.md`](docs/otf-deploy.md)

### Backend staging (`GCP/backend-staging`)

- Builds/pushes `.../oatmeal-farm-registry/backend:<short-sha>`
- Deploys with command override: **`uvicorn app.main:app`** (not `server_all`)
- Env: `SKIP_SCHEMA_ENSURE=true`, `INSTANCE_CONNECTION_NAME=<prod SQL connection name>`
- Secrets: `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY`
- **Docs-only** pushes under `docs/` do **not** trigger deploy (`paths-ignore`)

→ Full runbook: [`docs/staging/BACKEND_STAGING_DEPLOY.md`](docs/staging/BACKEND_STAGING_DEPLOY.md)

### Saige staging (`GCP/saige-staging`)

- Builds `saige/Dockerfile.backend` → `.../oatmeal-farm-registry/saige:<sha>`
- Triggers on changes to `saige/**` or `deploy-saige.yml` (plus manual `workflow_dispatch`)
- Runtime SA: `saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com`
- Vertex env + secrets `SECRET_KEY`, `CRON_SECRET`

→ Full runbook: [`docs/staging/SAIGE_STAGING_DEPLOY.md`](docs/staging/SAIGE_STAGING_DEPLOY.md)

### GitHub secrets (shared WIF)

| Secret | Used by |
|--------|---------|
| `STAGING_GCP_PROJECT_ID` | Both |
| `STAGING_GCP_SERVICE_ACCOUNT` | Both |
| `STAGING_GCP_WORKLOAD_IDENTITY_PROVIDER` | Both |

### Day-to-day merge targets

| Change type | Merge / push to |
|-------------|-----------------|
| Main API (`app/`, root Dockerfile, backend workflow) | `GCP/backend-staging` |
| Saige (`saige/`, Saige workflow) | `GCP/saige-staging` |
| Oatsense (`oatsense/`, precision-ag routers, Oatsense workflow) | `GCP/backend-staging` (path-filtered) or workflow_dispatch |
| Oatsense production promote | `GCP/oatsense-prod`, tag `oatsense-v*`, or workflow_dispatch |
| OTF Social (`otf/`, `app/routers/mill.py`) | `GCP/backend-staging` (path-filtered) or workflow_dispatch |
| Docs only (`docs/`) | Either; backend CD skips `docs/**` |

Do **not** expect a Saige code change on `GCP/backend-staging` to update `oatmeal-saige-staging`.
Oatsense staging **does** deploy from `GCP/backend-staging` when `oatsense/**` or its precision-ag path filters change.
OTF staging **does** deploy from `GCP/backend-staging` when `otf/**` or `app/routers/mill.py` change.

---

## Database (staging)

Staging does **not** use a writable staging Postgres DB.

- Connects **read-only** to prod Cloud SQL **SQL Server**: `animated-flare-421518:us-central1:oatmealailive` / `Oatmealailivedb`
- Runtime SA: `stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com`
- On Cloud Run: **Cloud SQL Python Connector** (not `127.0.0.1:1433` Auth Proxy TCP)
- SQL role: `db_datareader` — writes/DDL fail by design

Details: [`docs/staging/STAGING_CLOUD_SQL_SETUP.md`](docs/staging/STAGING_CLOUD_SQL_SETUP.md)

---

## Documentation index

| Doc | Topic |
|-----|--------|
| [`docs/staging/BACKEND_STAGING_DEPLOY.md`](docs/staging/BACKEND_STAGING_DEPLOY.md) | Backend staging CD, env, troubleshooting |
| [`docs/staging/SAIGE_STAGING_DEPLOY.md`](docs/staging/SAIGE_STAGING_DEPLOY.md) | Saige staging CD |
| [`docs/staging/STAGING_CLOUD_SQL_SETUP.md`](docs/staging/STAGING_CLOUD_SQL_SETUP.md) | RO→prod SQL, secrets, SA |
| [`docs/staging/SAIGE_STAGING_SETUP.md`](docs/staging/SAIGE_STAGING_SETUP.md) | Saige service / IAM notes |
| [`docs/cloud-run-staging.md`](docs/cloud-run-staging.md) | Staging service URLs / status |
| [`docs/iam-setup.md`](docs/iam-setup.md) | WIF, runtime SAs, roles |
| [`docs/oatsense-deploy.md`](docs/oatsense-deploy.md) | Oatsense staging + production CD, cutover |
| [`docs/otf-deploy.md`](docs/otf-deploy.md) | Over the Fence Social staging CD (livestock-style) |
| [`saige/README.md`](saige/README.md) | Saige product / API deep dive |

---

## API overview

JWT via `Authorization: Bearer <token>` on protected routes. Interactive docs: `/docs` when the server is running.

Major domains (prefixes vary by router): livestock, crops/precision-ag, produce/harvest, marketplace, supply-chain, events, accounting, website/blog, HR, ESG/compliance, and Saige chat APIs when that service is up.

---

## Technologies

| Layer | Stack |
|-------|--------|
| API | FastAPI, Uvicorn |
| DB | SQL Server — `pymssql` locally; Cloud SQL Python Connector + `pytds` on staging Cloud Run |
| Auth | JWT (`SECRET_KEY`) |
| Saige | LangGraph, Gemini / Vertex AI, Firestore, Redis (optional) |
| Deploy | Cloud Run, Artifact Registry, GitHub Actions + Workload Identity Federation |
| Payments / email | Stripe, SendGrid (where configured) |

---

## Development

### Tests

```bash
pytest
pytest test/UnitTest -v
pytest test/SmokeTest -v
```

### Router pattern

```python
from fastapi import APIRouter, Depends
from app.database import get_db

router = APIRouter(prefix="/api/example", tags=["example"])

@router.get("/")
def list_items(db=Depends(get_db)):
    ...
```

Register from `app/main.py` via `app.include_router(...)`.

### Seed / utility scripts

Legacy seed scripts may live at repo root; prefer documented scripts under `scripts/` for new work. Always point them at a **non-production** database unless you intentionally use the RO staging path (writes will fail).

---

## Security

**Never commit:**

- `.env`, service account JSON, live DB passwords

**Staging notes:**

- Staging holds a path to **live prod data** (read-only). Treat `DB_*` secrets carefully.
- Do not grant `db_datawriter` / `db_ddladmin` to the staging RO SQL login.
- GitHub Actions must not embed DB passwords in CI logs; staging CD mounts Secret Manager at deploy time.

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| `ModuleNotFoundError: routers` / `dependencies` | Use `app.routers` / `app.dependencies` |
| `Connection refused` to `127.0.0.1` on Cloud Run | Need `INSTANCE_CONNECTION_NAME` + Connector image (not localhost proxy) |
| `Login failed for user '<SQL_LOGIN>'` | Secret Manager still has a placeholder — set real `DB_USER` / `DB_PASSWORD` |
| `UPDATE/CREATE permission denied` on staging | Expected for RO login |
| `Set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT` on backend staging | Service is still running `server_all` — staging must use `app.main:app` |
| Backend CD ran on docs-only change | Ensure change is only under `docs/**` on `GCP/backend-staging` |
| Saige CD did not run | Push must hit `GCP/saige-staging` and change `saige/**` (or the Saige workflow) |

More detail: [`docs/staging/BACKEND_STAGING_DEPLOY.md`](docs/staging/BACKEND_STAGING_DEPLOY.md#troubleshooting).

---

## Related repositories

- Frontend: [oatmeal-farm-network-frontend](https://github.com/Oatmeal-Farm-Network/oatmeal-farm-network-frontend)
- Docs site: [oatmeal-farm-network-docs](https://github.com/Oatmeal-Farm-Network/oatmeal-farm-network-docs)

## License

See repository license / organization policy.
