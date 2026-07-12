# Saige Staging Deployment

**Owner:** Bringesh / Sankeerth  
**GCP project:** `oatmeal-farm-staging`  
**Region:** `us-central1`  
**Branch:** `GCP/saige-staging`  
**Workflow:** `.github/workflows/deploy-saige.yml`  
**Last updated:** July 2026

---

## What this deploys

| Item | Value |
|------|--------|
| Cloud Run service | `oatmeal-saige-staging` |
| Image | `us-central1-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/saige:<12-char-sha>` |
| Dockerfile | `saige/Dockerfile.backend` (build context `./saige`) |
| Runtime SA | `saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com` |
| Main backend | **Not deployed here** — use `GCP/backend-staging` + [BACKEND_STAGING_DEPLOY.md](./BACKEND_STAGING_DEPLOY.md) |

---

## How CD works

```text
push to GCP/saige-staging
        │
        ├─ only non-saige paths? ──► skip (paths filter)
        │
        ▼
GitHub Actions: Deploy Saige Staging
        │
        ├─ Auth via WIF (same secrets as backend staging)
        ├─ docker build -f saige/Dockerfile.backend ./saige
        ├─ push → Artifact Registry (:sha)
        └─ gcloud run deploy oatmeal-saige-staging
```

**Triggers:**

- `push` to `GCP/saige-staging` when files under `saige/**` or `.github/workflows/deploy-saige.yml` change
- `workflow_dispatch` (manual redeploy)

**Does not run** on `GCP/backend-staging` pushes.

---

## GitHub secrets / vars

| Name | Type | Purpose |
|------|------|---------|
| `STAGING_GCP_PROJECT_ID` | secret | Staging project |
| `STAGING_GCP_SERVICE_ACCOUNT` | secret | Deployer SA for WIF |
| `STAGING_GCP_WORKLOAD_IDENTITY_PROVIDER` | secret | WIF provider (same name as backend workflow) |
| `STAGING_REGION` | var (optional) | Default `us-central1` |
| `STAGING_ARTIFACT_REGISTRY_REPOSITORY` | var (optional) | Default `oatmeal-farm-registry` |
| `STAGING_FRONTEND_URL` | var (optional) | CORS / frontend URL for Saige |

Cloud Run also mounts secrets `SECRET_KEY` and `CRON_SECRET` from Secret Manager in the staging project.

---

## Operator process

1. Create/update work on a feature branch, then merge or push to **`GCP/saige-staging`** (not `GCP/backend-staging`).
2. Wait for **Deploy Saige Staging** in GitHub Actions.
3. Confirm URL and image:

```bash
gcloud run services describe oatmeal-saige-staging \
  --project=oatmeal-farm-staging --region=us-central1 \
  --format='yaml(status.url,spec.template.spec.containers[0].image)'
```

4. Manual redeploy without code change: Actions → **Deploy Saige Staging** → Run workflow (select `GCP/saige-staging`).

---

## Related

- [SAIGE_STAGING_SETUP.md](./SAIGE_STAGING_SETUP.md) — service/IAM/secrets status
- [BACKEND_STAGING_DEPLOY.md](./BACKEND_STAGING_DEPLOY.md) — main backend CD
- [../cloud-run-staging.md](../cloud-run-staging.md) — staging service URLs
