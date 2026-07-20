# Backend Staging Deployment

**Owner:** Bringesh  
**GCP project:** `oatmeal-farm-staging`  
**Region:** `us-central1`  
**Branch:** `GCP/backend-staging`  
**Workflow:** `.github/workflows/deploy-staging.yml`  
**Last updated:** July 2026

---

## What staging deploys

| Item | Value |
|------|--------|
| Cloud Run service | `oatmeal-backend-staging` |
| Image | `us-central1-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:<short-sha>` |
| Process | **Backend only** — `uvicorn app.main:app` (not `server_all`) |
| Saige | **Out of scope** — separate Cloud Run service + CD |
| Database | Read-only → prod Cloud SQL SQL Server (see [STAGING_CLOUD_SQL_SETUP.md](./STAGING_CLOUD_SQL_SETUP.md)) |

Dockerfile default `CMD` is still `server_all:app` (local/unified). Staging **overrides** command/args in the deploy workflow so Saige LLM secrets are not required on this service.

---

## How CD works

```text
push to GCP/backend-staging
        │
        ├─ only docs/** changed? ──► skip workflow (no build/deploy)
        │
        ▼
GitHub Actions: Deploy to Staging
        │
        ├─ Auth via Workload Identity Federation
        │     secrets: STAGING_GCP_WORKLOAD_IDENTITY_PROVIDER
        │              STAGING_GCP_SERVICE_ACCOUNT
        │              STAGING_GCP_PROJECT_ID
        ├─ docker build + push → Artifact Registry (:short-sha)
        └─ gcloud run deploy oatmeal-backend-staging
              image, RO SA, secrets, env, command override
```

**Docs skip:** `paths-ignore: docs/**` — a push that only touches files under `docs/` does not run CD. A push that mixes `docs/` with app/workflow changes **does** deploy.

### Runtime wiring (set by workflow)

| Setting | Value |
|---------|--------|
| Service account | `stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com` |
| `--set-cloudsql-instances` | `animated-flare-421518:us-central1:oatmealailive` (optional with Connector; kept for IAM/compat) |
| Command | `uvicorn` |
| Args | `app.main:app,--host,0.0.0.0,--port,8080` |
| Secrets | `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY` |
| Env | `SKIP_SCHEMA_ENSURE=true` |
| Env | `INSTANCE_CONNECTION_NAME=animated-flare-421518:us-central1:oatmealailive` |
| Env | `FRONTEND_URL` → staging frontend (password-reset links); default `https://oatmeal-frontend-staging-1087130530284.us-central1.run.app` or repo var `STAGING_FRONTEND_URL` |
| Min instances | `1` |

CORS allows the staging frontend origins in `app/main.py` (`ALLOWED_ORIGINS`).

### GitHub secrets required

| Secret | Purpose |
|--------|---------|
| `STAGING_GCP_PROJECT_ID` | Staging GCP project id |
| `STAGING_GCP_SERVICE_ACCOUNT` | Deployer SA for WIF |
| `STAGING_GCP_WORKLOAD_IDENTITY_PROVIDER` | WIF provider resource name |

---

## Database connection (Cloud Run)

Staging does **not** rely on Auth Proxy listening on `127.0.0.1:1433`.

When `INSTANCE_CONNECTION_NAME` is set, `app/database.py` uses the **Cloud SQL Python Connector** + `pytds`:

```text
Cloud Run (oatmeal-backend-staging)
  runtime SA → roles/cloudsql.client on prod
       │
       ▼
  google.cloud.sql.connector (in-process)
       │
       ▼
  Prod SQL Server: animated-flare-421518:us-central1:oatmealailive
  DB: Oatmealailivedb (db_datareader only)
```

| Mode | Trigger | Driver |
|------|---------|--------|
| Cloud Run / staging | `INSTANCE_CONNECTION_NAME` set | Connector + `pytds` |
| Local / no instance name | unset | `pymssql` → `DB_SERVER` |

`DB_SERVER=127.0.0.1` may still exist in Secret Manager but is **ignored** when the Connector path is active.

`SKIP_SCHEMA_ENSURE=true` skips DDL helpers that use `app/schema_ensure.py`. Some older routers still attempt import-time setup behind try/except; **writes fail by design** (RO login) and must not crash the process.

---

## Deploy process (operators)

### Normal path (preferred)

1. Merge/push changes to `GCP/backend-staging`.
2. Wait for Actions workflow **Deploy to Staging** to succeed.
3. Confirm service URL and revision image tag (`:short-sha`).

```bash
gcloud run services describe oatmeal-backend-staging \
  --project=oatmeal-farm-staging --region=us-central1 \
  --format='yaml(status.url,spec.template.spec.containers[0].image,spec.template.spec.containers[0].command,spec.template.spec.containers[0].args)'
```

4. Check logs:

```bash
gcloud run services logs read oatmeal-backend-staging \
  --project=oatmeal-farm-staging --region=us-central1 --limit=50
```

Expect Uvicorn listening on 8080 and **no** Saige `GOOGLE_API_KEY` / `server_all` load.

### Manual secret update (does not rebuild image)

```bash
# After fixing secret values, roll a revision that remounts :latest
gcloud run services update oatmeal-backend-staging \
  --project=oatmeal-farm-staging --region=us-central1 \
  --update-secrets=DB_USER=DB_USER:latest,DB_PASSWORD=DB_PASSWORD:latest,DB_NAME=DB_NAME:latest
```

`--update-secrets` alone keeps the **current image**. To pick up code fixes you need a new image deploy (Actions or `gcloud run deploy --image=...:sha`).

### Verify secrets are not placeholders

```bash
gcloud secrets versions access latest --secret=DB_USER --project=oatmeal-farm-staging | od -c
# Must NOT be literal: <SQL_LOGIN>
gcloud secrets versions access latest --secret=DB_NAME --project=oatmeal-farm-staging
# Expect: Oatmealailivedb
```

---

## App changes made for staging boot (summary)

| Change | Why |
|--------|-----|
| Lazy `_ensure_schema` + `SKIP_SCHEMA_ENSURE` | Avoid import-time DDL / DB connect on RO staging |
| Rewrite `from routers.X` → `from app.routers.X` | Package layout in Docker |
| Rewrite `from dependencies` → `from app.dependencies` | Same |
| Fix bare `__import__('database')` in `events.py` | Crash on import |
| Cloud SQL Python Connector in `database.py` | Cloud Run never exposed `127.0.0.1:1433` for SQL Server |
| Deploy command → `app.main:app` | Skip Saige; Saige has its own CD |
| Re-encode Windows-1252 routers as UTF-8 | Linux/Docker Source encoding SyntaxError |

Branch used for this work: `GCP/backend-staging` (from `epic/backend-reorg`).

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `Connection refused` on `127.0.0.1` | Old image without Connector / missing `INSTANCE_CONNECTION_NAME` | Redeploy from current workflow |
| `Login failed for user '<SQL_LOGIN>'` | Placeholder in `DB_USER` / bad password | Fix Secret Manager values; update service |
| `UPDATE/CREATE permission was denied` | Expected for `db_datareader` | Ignore if request handlers still work for reads |
| `No authentication found. Set GOOGLE_API_KEY` | Running `server_all:app` | Confirm Cloud Run command is `app.main:app` |
| `utf-8` / `0x96` SyntaxError in routers | Non-UTF-8 source in image | Ensure latest branch image with UTF-8 fix |
| `--update-secrets` then “failed to listen on 8080” | Same broken image + secret-only roll | Deploy new image SHA from CD |
| Cloud Shell `Gaia id not found` | Shell identity quirk | Ignore if command still returns data |

---

## Related docs

- [STAGING_CLOUD_SQL_SETUP.md](./STAGING_CLOUD_SQL_SETUP.md) — RO→prod SQL, SA, secrets
- [../cloud-run-staging.md](../cloud-run-staging.md) — service URLs / status
- [./SAIGE_STAGING_SETUP.md](./SAIGE_STAGING_SETUP.md) — Saige staging (separate pipeline)
- [../iam-setup.md](../iam-setup.md) — WIF + runtime SA roles
