# Saige Staging Setup

**Owner:** Sankeerth  
**Project:** `oatmeal-farm-staging`  
**Service:** `oatmeal-saige-staging`  
**Region:** `us-central1`  
**Last updated:** July 12, 2026

> Scope is staging only. Do not create or modify production secrets or services from this runbook.

---

## Current Scope

Backend DB secrets and backend Cloud Run DB wiring are already owned and documented under:

- [`docs/staging/STAGING_CLOUD_SQL_SETUP.md`](/Users/sankeerthpalakurthy/Desktop/oatmealfarmnetworkbackend-saige/docs/staging/STAGING_CLOUD_SQL_SETUP.md)

Sankeerth owns only:

- the Saige Cloud Run service
- Saige-specific secret wiring
- the Saige portion of the secret-to-service map

### Image / entrypoint

Saige images build from `saige/Dockerfile.backend` with context `./saige`.

- Must copy the **full package** (`COPY . .`) — not root `*.py` only.
- Process entry remains **`uvicorn api:app`** (root shim → `app.api:app`).
- Workflow: `.github/workflows/deploy-saige.yml`; helper: `saige/deploy.ps1`.
- Layout notes: [`saige/docs/MIGRATION_RESULTS.md`](../../saige/docs/MIGRATION_RESULTS.md).

---

## Current Staging Status

### Cloud Run service

`oatmeal-saige-staging` exists in staging and is configured with:

| Field | Value |
| --- | --- |
| URL | `https://oatmeal-saige-staging-lrviw4iujq-uc.a.run.app` |
| Runtime SA | `saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com` |
| Min instances | `1` |
| CPU | `2` |
| Memory | `2Gi` |

### Important limitation

The service is still running the placeholder image:

```text
us-docker.pkg.dev/cloudrun/container/hello
```

That happened because:

- `cloudbuild.googleapis.com` was disabled initially
- it is now enabled
- the current user still does not have permission to submit Cloud Build jobs in staging

### Public access

The service URL currently returns `403`.

`allow-unauthenticated` was requested at deploy time, but the current user does not have `run.services.setIamPolicy`, so `allUsers -> roles/run.invoker` could not be applied.

---

## Enabled Staging APIs Relevant To Saige

These APIs are enabled in `oatmeal-farm-staging`:

- `run.googleapis.com`
- `artifactregistry.googleapis.com`
- `secretmanager.googleapis.com`
- `sqladmin.googleapis.com`
- `cloudbuild.googleapis.com`
- `firestore.googleapis.com`
- `aiplatform.googleapis.com`

---

## Secrets

### Existing app/shared secrets in staging

| Secret | Notes |
| --- | --- |
| `SECRET_KEY` | Shared JWT secret for backend + Saige |
| `DB_SERVER` | Backend RO SQL Server path; owned by backend DB work |
| `DB_USER` | Backend RO SQL Server path; owned by backend DB work |
| `DB_PASSWORD` | Backend RO SQL Server path; owned by backend DB work |
| `DB_NAME` | Backend RO SQL Server path; owned by backend DB work |

### Existing deprecated secrets

| Secret | Notes |
| --- | --- |
| `staging-db-connection-string` | Old Postgres secret; do not wire to app services |
| `staging-db-password` | Old Postgres secret; do not wire to app services |

### Saige-specific secrets created for staging

| Secret | Used by | Notes |
| --- | --- | --- |
| `CRON_SECRET` | Saige | Protects cron-triggered Saige endpoints |

### Saige-specific secrets still not provisioned

These are optional or runtime-dependent and were not created in staging because no approved values were available:

| Secret | Why it might be needed |
| --- | --- |
| `GOOGLE_API_KEY` | Only if Saige should use Gemini Developer API instead of Vertex AI |
| `GEMINI_API_KEY` | Same as above; fallback alias in code |
| `WEATHER_API_KEY` | Required for weather-provider integrations |
| `REDIS_URL` | Required only if Redis-backed buffering/checkpointing is enabled |

---

## Current Saige Runtime Wiring

The Saige service is currently configured with these plain env vars:

| Variable | Value |
| --- | --- |
| `GOOGLE_CLOUD_PROJECT` | `oatmeal-farm-staging` |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` |
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` |
| `VERTEX_AI_MODEL` | `gemini-2.5-flash-lite` |
| `FIRESTORE_DATABASE` | `charlie` |
| `CHAT_HISTORY_DATABASE` | `chat-history` |
| `REDIS_ENABLED` | `false` |
| `FRONTEND_URL` | `https://oatmeal-frontend-staging-lrviw4iujq-uc.a.run.app` |
| `ALLOW_ALL_ORIGINS` | `false` |

The Saige service is currently configured with these secret mounts:

| Env var | Secret |
| --- | --- |
| `SECRET_KEY` | `SECRET_KEY` |
| `CRON_SECRET` | `CRON_SECRET` |

---

## Secret To Service Map

### Backend

Owned by backend DB work:

| Service | Secrets |
| --- | --- |
| `oatmeal-backend-staging` | `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY` |

### Saige

Currently mounted:

| Service | Secrets |
| --- | --- |
| `oatmeal-saige-staging` | `SECRET_KEY`, `CRON_SECRET` |

Potential future mounts if values are provided:

| Service | Secrets |
| --- | --- |
| `oatmeal-saige-staging` | `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `WEATHER_API_KEY`, `REDIS_URL` |

### Frontend

No backend/Saige secrets are documented as mounted on `oatmeal-frontend-staging` from this task.

---

## Saige Runtime IAM Notes

`saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com` currently has:

- `roles/cloudsql.client`
- `roles/secretmanager.secretAccessor`

That is enough for the currently mounted secrets, but a real Saige runtime that uses Vertex AI and Firestore will also require corresponding runtime access in staging.

This is an inference from the code and enabled APIs:

- Vertex AI access likely needs a role such as `roles/aiplatform.user`
- Firestore access likely needs a Firestore/Datastore role

Those IAM grants were not applied from this task because the current user does not have project IAM admin rights.

---

## Remaining Live GCP Blockers

1. Build and deploy the real Saige image to Artifact Registry
   - `cloudbuild.googleapis.com` is enabled
   - current user still gets `PERMISSION_DENIED` on `gcloud builds submit`

2. Make Saige publicly invokable if that is still the team requirement
   - current user gets `PERMISSION_DENIED` on `run.services.setIamPolicy`

3. If real Saige features should run in staging, grant runtime IAM needed for:
   - Vertex AI
   - Firestore

4. Create optional Saige secrets only if approved values are provided:
   - `GOOGLE_API_KEY`
   - `GEMINI_API_KEY`
   - `WEATHER_API_KEY`
   - `REDIS_URL`

---

## Verify Commands

### Service config

```bash
gcloud run services describe oatmeal-saige-staging \
  --project oatmeal-farm-staging \
  --region us-central1 \
  --format="yaml(spec.template.metadata.annotations,spec.template.spec.serviceAccountName,spec.template.spec.containers,status.url)"
```

### Service URL

```bash
gcloud run services describe oatmeal-saige-staging \
  --project oatmeal-farm-staging \
  --region us-central1 \
  --format='value(status.url)'
```

### Secret inventory

```bash
gcloud secrets list \
  --project oatmeal-farm-staging \
  --format='table(name,createTime)'
```
