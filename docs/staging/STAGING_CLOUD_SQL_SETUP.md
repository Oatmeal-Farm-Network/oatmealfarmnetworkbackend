# Staging Database Setup

**Owner:** Bringesh (updated with RO→prod design)
**GCP staging project:** `oatmeal-farm-staging`
**Last updated:** July 2026

> **Important:** Staging does **not** use a separate writable app database.
> The staging backend connects **read-only** to the **production** Cloud SQL
> SQL Server instance via Cloud SQL Auth Proxy.

---

## Architecture

```
Cloud Run (oatmeal-backend-staging)
  runtime SA: stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com
       │
       ├─ Cloud SQL Auth Proxy  (--set-cloudsql-instances)
       │         │
       │         ▼
       │   127.0.0.1:1433
       ▼
  pymssql (DB_USER / DB_PASSWORD / DB_NAME)
       │
       ▼
  Prod Cloud SQL SQL Server
  Project: animated-flare-421518
  Instance: oatmealailive
  Database: Oatmealailivedb
  DB role: db_datareader only
```

**Connection name (for Cloud Run / proxy):**

```text
animated-flare-421518:us-central1:oatmealailive
```

---

## Why not PostgreSQL?

The original sprint task said “Cloud SQL PostgreSQL.” That was incorrect.

- Production DB is **SQL Server**
- The app uses `mssql+pymssql` with `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
  (see `app/database.py`)

A leftover Postgres instance may still exist in staging:

| Instance | Version | Notes |
|----------|---------|--------|
| `oatmeal-staging-db` | POSTGRES_15 | **Deprecated** — stop/delete; not used by the app |

---

## Service account

| Field | Value |
|-------|--------|
| Email | `stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com` |
| Purpose | Staging → prod DB read-only via Auth Proxy |
| Prod IAM | `roles/cloudsql.client` on `animated-flare-421518` |
| SQL Server | Login mapped to user in `Oatmealailivedb` with `db_datareader` only |

Verified: `SELECT` works; `CREATE TABLE` is denied.

---

## Secret Manager (staging project)

App secrets (use these — not the old Postgres secrets):

| Secret | Value / meaning |
|--------|------------------|
| `DB_SERVER` | `127.0.0.1` (Auth Proxy local endpoint on Cloud Run) |
| `DB_USER` | RO SQL Server login |
| `DB_PASSWORD` | RO SQL login password |
| `DB_NAME` | `Oatmealailivedb` |
| `SECRET_KEY` | App secret key |

**Deprecated (do not wire to Cloud Run):**

| Secret | Notes |
|--------|--------|
| `staging-db-connection-string` | Old Postgres connection string |
| `staging-db-password` | Old Postgres password |

Grant `roles/secretmanager.secretAccessor` on the `DB_*` (+ `SECRET_KEY`) secrets to the RO SA above.

---

## Cloud Run wiring (backend)

```bash
gcloud run services update oatmeal-backend-staging \
  --project=oatmeal-farm-staging \
  --region=us-central1 \
  --service-account=stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com \
  --set-cloudsql-instances=animated-flare-421518:us-central1:oatmealailive \
  --update-secrets=DB_SERVER=DB_SERVER:latest,DB_USER=DB_USER:latest,DB_PASSWORD=DB_PASSWORD:latest,DB_NAME=DB_NAME:latest,SECRET_KEY=SECRET_KEY:latest
```

---

## Local / Cloud Shell verify (Auth Proxy)

```bash
CONNECTION_NAME="animated-flare-421518:us-central1:oatmealailive"

# Terminal 1 — proxy (impersonate RO SA)
docker run --rm -p 1433:1433 \
  gcr.io/cloud-sql-connectors/cloud-sql-proxy:latest \
  --address 0.0.0.0 --port 1433 \
  --impersonate-service-account=stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com \
  "$CONNECTION_NAME"

# Terminal 2 — read check
docker run -it --rm --network host mcr.microsoft.com/mssql-tools \
  /opt/mssql-tools/bin/sqlcmd \
  -S 127.0.0.1,1433 -U '<DB_USER>' -P '<DB_PASSWORD>' -d Oatmealailivedb \
  -Q "SELECT TOP 1 name FROM sys.tables"
```

---

## APIs enabled (staging)

| API | Purpose |
|-----|---------|
| Cloud Run | Staging services |
| Cloud SQL Admin | Manage / connect (client path) |
| Artifact Registry | Docker images |
| IAM | Service accounts |
| Secret Manager | `DB_*` / `SECRET_KEY` |

---

## Setup status

| Task | Status |
|------|--------|
| Staging GCP project + billing | ✅ Done |
| Required APIs enabled | ✅ Done |
| RO SA + prod `cloudsql.client` | ✅ Done |
| SQL login + `db_datareader` on `Oatmealailivedb` | ✅ Done |
| Auth Proxy read path verified | ✅ Done |
| `DB_*` secrets in Secret Manager | ✅ Done (`DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`) |
| Cloud Run SA + Cloud SQL + secrets attached | ✅ Done (`oatmeal-backend-staging`) |
| Stop Postgres `oatmeal-staging-db` | ✅ Done (`activationPolicy=NEVER`, `STOPPED`) — delete later if desired |
| Docs updated | ✅ This PR |
| Deprecated secrets `staging-db-*` | ⏳ Optional cleanup (do not wire to Cloud Run) |

---

## Security notes

- Staging holds a **path to live prod data** (read-only). Treat staging credentials carefully.
- Do **not** grant `db_datawriter` / `db_ddladmin` to this login.
- GitHub Actions CI must **not** use these secrets (boot-check stays DB-less).
- Write-path smoke tests against this DB will fail by design.
