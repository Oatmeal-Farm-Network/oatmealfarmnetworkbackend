# Staging Database Setup

**Owner:** Bringesh (updated with RO→prod design)
**GCP staging project:** `oatmeal-farm-staging`
**Last updated:** July 2026

> **⚠️ SUPERSEDED (July 2026):** Staging no longer connects read-only to prod.
> It now uses its own **writable** Cloud SQL SQL Server instance
> (`oatmeal-staging-sqlserver`) cloned from prod. See
> [STAGING_WRITABLE_DB.md](./STAGING_WRITABLE_DB.md) for the current design.
> The read-only design below is kept for historical reference only.

---

## Architecture

```
Cloud Run (oatmeal-backend-staging)
  runtime SA: stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com
  env: INSTANCE_CONNECTION_NAME=animated-flare-421518:us-central1:oatmealailive
       │
       ▼
  app/database.py → Cloud SQL Python Connector + pytds
       │
       ▼
  Prod Cloud SQL SQL Server
  Project: animated-flare-421518
  Instance: oatmealailive
  Database: Oatmealailivedb
  DB role: db_datareader only
```

**Local / without `INSTANCE_CONNECTION_NAME`:** `pymssql` connects to `DB_SERVER` (e.g. Auth Proxy on a laptop).

**Connection name:**

```text
animated-flare-421518:us-central1:oatmealailive
```

### Why not Auth Proxy on `127.0.0.1:1433` on Cloud Run?

`--set-cloudsql-instances` was configured and IAM/API/public IP were correct, but the
container never got a listener on `127.0.0.1:1433` (SQL Server + Cloud Run).
The Python Connector opens the secure path in-process and does not need that port.

---

## Why not PostgreSQL?

The original sprint task said “Cloud SQL PostgreSQL.” That was incorrect.

- Production DB is **SQL Server**
- The app uses SQL Server drivers via `app/database.py` (`pymssql` locally;
  Connector + `pytds` when `INSTANCE_CONNECTION_NAME` is set)

A leftover Postgres instance may still exist in staging:

| Instance | Version | Notes |
|----------|---------|--------|
| `oatmeal-staging-db` | POSTGRES_15 | **Deprecated** — stop/delete; not used by the app |

---

## Service account

| Field | Value |
|-------|--------|
| Email | `stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com` |
| Purpose | Staging → prod DB read-only (Connector / client IAM) |
| Prod IAM | `roles/cloudsql.client` on `animated-flare-421518` |
| SQL Server | Login mapped to user in `Oatmealailivedb` with `db_datareader` only |

Verified: `SELECT` works; `CREATE TABLE` / `UPDATE` are denied.

---

## Secret Manager (staging project)

App secrets (use these — not the old Postgres secrets):

| Secret | Value / meaning |
|--------|------------------|
| `DB_SERVER` | Legacy / local (`127.0.0.1`). **Ignored on Cloud Run** when `INSTANCE_CONNECTION_NAME` is set |
| `DB_USER` | RO SQL Server login (**must be real — not `<SQL_LOGIN>`**) |
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

Prefer the CD workflow (sets command override + `INSTANCE_CONNECTION_NAME`). Equivalent core flags:

```bash
gcloud run deploy oatmeal-backend-staging \
  --project=oatmeal-farm-staging \
  --region=us-central1 \
  --service-account=stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com \
  --set-cloudsql-instances=animated-flare-421518:us-central1:oatmealailive \
  --command=uvicorn \
  --args=app.main:app,--host,0.0.0.0,--port,8080 \
  --update-secrets=DB_SERVER=DB_SERVER:latest,DB_USER=DB_USER:latest,DB_PASSWORD=DB_PASSWORD:latest,DB_NAME=DB_NAME:latest,SECRET_KEY=SECRET_KEY:latest \
  --update-env-vars=SKIP_SCHEMA_ENSURE=true,INSTANCE_CONNECTION_NAME=animated-flare-421518:us-central1:oatmealailive \
  --min-instances=1
```

---

## Local / Cloud Shell verify (Auth Proxy)

Useful to prove IAM + SQL login **outside** Cloud Run:

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
| Cloud SQL Admin | Connector / client path (`sqladmin.googleapis.com`) |
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
| Local Auth Proxy read path verified | ✅ Done |
| Cloud Run Python Connector path | ✅ Done (`INSTANCE_CONNECTION_NAME` + `cloud-sql-python-connector`) |
| `DB_*` secrets in Secret Manager | ✅ Done (replace any `<SQL_LOGIN>` placeholders) |
| Cloud Run SA + secrets + backend-only CMD | ✅ Done (`oatmeal-backend-staging`) |
| Stop Postgres `oatmeal-staging-db` | ✅ Done (`activationPolicy=NEVER`, `STOPPED`) — delete later if desired |
| Deprecated secrets `staging-db-*` | ⏳ Optional cleanup (do not wire to Cloud Run) |

---

## Security notes

- Staging holds a **path to live prod data** (read-only). Treat staging credentials carefully.
- Do **not** grant `db_datawriter` / `db_ddladmin` to this login.
- GitHub Actions CI must **not** use these secrets (boot-check stays DB-less).
- Write-path smoke tests against this DB will fail by design.
