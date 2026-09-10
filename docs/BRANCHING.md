# Backend — Git train

This repo follows the Oatmeal AI three-environment train. Do not rename these branches.

```text
feature/*  →  PR  →  GCP/backend-staging  →  PR  →  GCP/backend-testing  →  PR  →  main
                         staging Cloud Run              testing Cloud Run              production
```

| Branch | Services | GCP project | Workflows |
|--------|----------|-------------|-----------|
| `GCP/backend-staging` | `oatmeal-backend-staging`, `oatmeal-saige-staging`, `oatmeal-livestock-staging`, `oatmeal-oatsense-staging` | `oatmeal-farm-staging` | `deploy-staging.yml`, `deploy-saige-staging.yml`, `deploy-livestock-staging.yml`, `deploy-oatsense-staging.yml` |
| `GCP/backend-testing` | `oatmeal-*-testing` (same four) | `oatmeal-farm-staging` | `deploy-testing.yml`, `deploy-saige-testing.yml`, `deploy-livestock-testing.yml`, `deploy-oatsense-testing.yml` |
| `main` | **`oatmealfarmnewtorkbackend`**, **`saige-backend`** | `animated-flare-421518` | `deploy-backend-prod.yml`, `deploy-saige.yml` |

Allowed PRs only:

1. Work branch → `GCP/backend-staging`
2. `GCP/backend-staging` → `GCP/backend-testing`
3. `GCP/backend-testing` → `main`

Cut work branches from **current staging**. `tests/backend-staging`, `Live`, and `live` are not environment branches.

CI (`.github/workflows/ci.yml`) runs on PRs into all three bases.

Testing CD stays fail-closed until isolated Cloud SQL / Firestore and `TESTING_*` exist in **`oatmeal-farm-staging`**. Never create testing or staging services in `animated-flare-421518`. Do not point testing at production `SECRET_KEY` or production DB passwords.

**Reconcile:** `GCP/backend-staging` and `main` still diverge (unique commits on both sides). Merge `main` into staging in a pairing session before treating testing as a production release candidate. Do not fast-forward `main` with the full staging delta.

### Official production Cloud Run (`animated-flare-421518` / Oatmeal AI)

| Surface | Service | Workflow |
|---------|---------|----------|
| Shared API | `oatmealfarmnewtorkbackend` (typo is the real name) | `deploy-backend-prod.yml` |
| Saige | `saige-backend` | `deploy-saige.yml` (gated by `PROD_SAIGE_DEPLOY_ENABLED` — do **not** set it yet) |

Do not deploy from `main` into `oatmeal-farm-staging`. Staging/testing Saige are `oatmeal-saige-staging` / `oatmeal-saige-testing` in the staging project only.

`deploy-livestock-prod.yml` (`oatmeal-livestock-prod`) and `deploy-oatsense-prod.yml` (`oatmeal-oatsense`) are **not** official prod surfaces — keep them fail-closed. Official LOA/Oatsense frontends live in their own repos.
