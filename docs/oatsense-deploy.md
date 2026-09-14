# Oatsense deploy runbook

Oatsense is a standalone FastAPI service in this repo (`oatsense/`) that owns
precision-ag / crop-detection APIs and proxies
[CropMonitorBackend](https://github.com/Oatmeal-Farm-Network/OatmealFarmNetworkCropMonitorBackend)
as a single BFF for the Oatsense website.

Local:

```bash
uvicorn oatsense.api:app --reload --port 8003
```

Health: `GET /health` → `{"status":"ok","service":"oatsense"}`

---

## Architecture

| Layer | Responsibility |
|-------|----------------|
| Oatsense Cloud Run | Precision-ag CRUD + field health/activity + CropMonitor HTTP proxy |
| CropMonitorBackend | Satellite/NDVI/WaPOR compute (separate repo) |
| Shared SQL Server | Field / analysis / notes tables (same DB as main backend) |

Proxy env: `CROP_MONITOR_URL`

- Explicit proxied paths (same as main backend today): water-use, agronomy,
  recommendations, analyses, analyze, indices/series, zones, raster,
  zones/prescription, email-analysis.
- Catch-all for remaining CropMonitor paths / tiles:
  ` /api/cm/{path}` → `{CROP_MONITOR_URL}/api/{path}`
  (use this when a CropMonitor path collides with precision-ag CRUD, e.g. alerts).

---

## Staging

| Item | Value |
|------|-------|
| Workflow | `.github/workflows/deploy-oatsense-staging.yml` |
| Branch trigger | `GCP/backend-staging` (path-filtered) + `workflow_dispatch` |
| Cloud Run | `oatmeal-oatsense-staging` |
| Image | `{region}-docker.pkg.dev/{project}/oatmeal-farm-registry/oatsense:<sha>` |
| Runtime SA | Same staging DB SA as livestock (`stg-to-prod-db-ro-dev-project@…`) |

### Staging GitHub vars / secrets

| Name | Type | Purpose |
|------|------|---------|
| `STAGING_GCP_PROJECT_ID` | secret | GCP project |
| `STAGING_GCP_SERVICE_ACCOUNT` | secret | Deploy SA (WIF) |
| `STAGING_GCP_WORKLOAD_IDENTITY_PROVIDER` | secret | WIF provider |
| `STAGING_REGION` | var | default `us-central1` |
| `STAGING_ARTIFACT_REGISTRY_REPOSITORY` | var | default `oatmeal-farm-registry` |
| `STAGING_OATSENSE_FRONTEND_URL` | var | CORS / `OATSENSE_FRONTEND_URL` (falls back to `STAGING_FRONTEND_URL`) |
| `STAGING_CROP_MONITOR_URL` | var | CropMonitor Cloud Run URL |

Secrets mounted on the service: `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY`
(same JWT secret as main backend so OFN tokens validate).

First-time create is done by the workflow’s `gcloud run deploy` (creates the
service if missing). After the first deploy, confirm:

```bash
gcloud run services describe oatmeal-oatsense-staging \
  --region us-central1 --project oatmeal-farm-staging \
  --format='value(status.url)'
curl -sS "$(gcloud run services describe oatmeal-oatsense-staging \
  --region us-central1 --project oatmeal-farm-staging \
  --format='value(status.url)')/health"
```

---

## Production

| Item | Value |
|------|-------|
| Workflow | `.github/workflows/deploy-oatsense-prod.yml` |
| Triggers | `workflow_dispatch`, push to `GCP/oatsense-prod`, tags `oatsense-v*` |
| Cloud Run | `oatmeal-oatsense` |
| Image | `{region}-docker.pkg.dev/{project}/oatmeal-farm-registry/oatsense:<sha>` |

**Do not auto-deploy from `main`.** Promote explicitly via dispatch, prod branch, or tag.

### Production prerequisites (one-time)

Prod CD is the first production workflow in this repo. Before the first run:

1. Confirm prod GCP project ID and region with the team.
2. Create Workload Identity Federation for GitHub Actions (deploy SA).
3. Create Cloud Run runtime SA with Cloud SQL client + Secret Manager accessor.
4. Create/confirm secrets in Secret Manager: `DB_*`, `SECRET_KEY` (match main backend JWT).
5. Create Artifact Registry repo (or grant reader on staging registry — see `docs/iam-setup.md`).
6. Set the GitHub secrets/vars below.
7. Run **Deploy Oatsense Production** via `workflow_dispatch`.

### Production GitHub secrets / vars

| Name | Type | Purpose |
|------|------|---------|
| `PROD_GCP_PROJECT_ID` | secret | Prod GCP project |
| `PROD_GCP_SERVICE_ACCOUNT` | secret | Deploy SA email |
| `PROD_GCP_WIF_PROVIDER` | secret | WIF provider resource name |
| `PROD_REGION` | var | default `us-central1` |
| `PROD_ARTIFACT_REGISTRY_REPOSITORY` | var | default `oatmeal-farm-registry` |
| `PROD_CLOUD_SQL_INSTANCE` | var | `project:region:instance` |
| `PROD_OATSENSE_RUNTIME_SA` | var | Cloud Run runtime SA email |
| `PROD_OATSENSE_FRONTEND_URL` | var | Oatsense website origin (CORS) |
| `PROD_CROP_MONITOR_URL` | var | Prod CropMonitor Cloud Run URL |

---

## Frontend cutover

| Consumer | Config |
|----------|--------|
| **New Oatsense website** | `VITE_OATSENSE_API_URL=<oatsense Cloud Run URL>` — single origin; do **not** set a separate CropMonitor URL. For CropMonitor-only colliding paths use `/api/cm/...`. |
| **OFN main frontend** | Keep `VITE_API_URL` + `VITE_CROP_API_URL` until product cutover. |
| **Main backend** | Continues mounting the same precision-ag / proxy routers during dual-serve. Remove from `app/main.py` only after Oatsense traffic is stable. |
| **Saige** | Keep SQL reads / `OFN_BACKEND_URL`. After cutover, optionally add `OATSENSE_URL` for computed precision-ag endpoints. |

Auth: Oatsense uses the same `SECRET_KEY` as the main backend so existing JWTs work. Login can remain on the main auth API; the Oatsense website calls Oatsense for field/crop APIs only.
