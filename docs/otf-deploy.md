# Over the Fence (OTF) Social deploy runbook

OTF is a **Saige-style isolated** FastAPI package in this repo (`otf/`).
It owns Over the Fence social: communities, channels, DMs, group DMs,
messages, and forums.

Local (from `otf/`):

```bash
cd otf
uvicorn api:app --reload --port 8004
```

Health: `GET /health` → `{"status":"ok","service":"otf"}`

Mill API prefix: `/api/admin/mill/*`

---

## Package layout (mirrors Saige)

```text
otf/
├── api.py                 # Shim → app.api:app  (uvicorn api:app)
├── app/
│   ├── api.py             # FastAPI app + CORS + /health
│   └── mill.py            # Communities / channels / DMs / forums
├── database.py            # SQL Server + Cloud SQL Connector
├── schema_ensure.py       # Lazy DDL gate (SKIP_SCHEMA_ENSURE)
├── requirements.txt       # Package-local deps
├── Dockerfile.backend     # Build context = ./otf
└── cloudbuild.yaml
```

Docker build context is **`./otf` only** — zero dependency on the rest of
the repo at image-build time (same rule as Saige).

Main backend still mounts [`app/routers/mill.py`](../app/routers/mill.py)
during dual-serve. After cutover, remove that include from `app/main.py`.

---

## Staging

| Item | Value |
|------|-------|
| Workflow | `.github/workflows/deploy-otf-staging.yml` |
| Triggers | push to `GCP/otf-staging` (path `otf/**`) + `workflow_dispatch` |
| Cloud Run | `oatmeal-otf-staging` |
| Image | `.../oatmeal-farm-registry/otf:<sha>` |
| Build | `docker build -f otf/Dockerfile.backend ./otf` |
| Runtime SA | `otf-sa@<project>.iam.gserviceaccount.com` |

### Staging secrets / vars

Shared WIF (same as Saige):

| Name | Type |
|------|------|
| `STAGING_GCP_PROJECT_ID` | secret |
| `STAGING_GCP_SERVICE_ACCOUNT` | secret |
| `STAGING_GCP_WIF_PROVIDER` | secret |
| `STAGING_OTF_FRONTEND_URL` | var (CORS; falls back to `STAGING_FRONTEND_URL`) |

Service mounts: `DB_*`, `SECRET_KEY`. Env: `INSTANCE_CONNECTION_NAME`,
`SKIP_SCHEMA_ENSURE=true`, `OTF_FRONTEND_URL`.

### One-time: create `otf-sa` (staging)

Mirror Saige’s `saige-sa` setup — Cloud SQL client + Secret Manager accessor:

```bash
gcloud iam service-accounts create otf-sa \
  --display-name="OTF Social runtime" \
  --project=oatmeal-farm-staging

# Grant Cloud SQL client + secret accessor (adjust roles to match saige-sa)
gcloud projects add-iam-policy-binding oatmeal-farm-staging \
  --member="serviceAccount:otf-sa@oatmeal-farm-staging.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

Smoke-test after first deploy:

```bash
curl -sS "$(gcloud run services describe oatmeal-otf-staging \
  --region us-central1 --project oatmeal-farm-staging \
  --format='value(status.url)')/health"
```

---

## Production

**Deferred.** Staging only for now — no `deploy-otf-prod.yml`. Add a production
workflow later when ready (mirror Saige/Oatsense prod patterns).

---

## Frontend cutover

| Consumer | Config |
|----------|--------|
| OTF UI | `VITE_OTF_API_URL=<otf Cloud Run URL>` |
| Main backend | Keep `mill` mounted until traffic moves; then drop from `app/main.py` |

Do **not** expect an OTF change on `GCP/backend-staging` to update
`oatmeal-otf-staging` — push to `GCP/otf-staging` (or dispatch) instead.
