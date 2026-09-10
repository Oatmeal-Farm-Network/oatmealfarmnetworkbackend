# Backend — Git train

This repo follows the Oatmeal AI three-environment train. Do not rename these branches.

```text
feature/*  →  PR  →  GCP/backend-staging  →  PR  →  GCP/backend-testing  →  PR  →  main
                         staging Cloud Run              testing Cloud Run              production
```

| Branch | Services | Workflows |
|--------|----------|-----------|
| `GCP/backend-staging` | `oatmeal-backend-staging`, `oatmeal-saige-staging`, `oatmeal-livestock-staging`, `oatmeal-oatsense-staging` | `deploy-staging.yml`, `deploy-saige-staging.yml`, `deploy-livestock-staging.yml`, `deploy-oatsense-staging.yml` |
| `GCP/backend-testing` | `oatmeal-*-testing` (same four) | `deploy-testing.yml`, `deploy-saige-testing.yml`, `deploy-livestock-testing.yml`, `deploy-oatsense-testing.yml` |
| `main` | production services | `deploy-backend-prod.yml`, `deploy-saige.yml`, `deploy-livestock-prod.yml`, `deploy-oatsense-prod.yml` |

Allowed PRs only:

1. Work branch → `GCP/backend-staging`
2. `GCP/backend-staging` → `GCP/backend-testing`
3. `GCP/backend-testing` → `main`

Cut work branches from **current staging**. `tests/backend-staging`, `Live`, and `live` are not environment branches.

CI (`.github/workflows/ci.yml`) runs on PRs into all three bases.

Testing CD stays fail-closed until isolated Cloud SQL / Firestore and `TESTING_*` exist. Do not point testing at production `SECRET_KEY` or production DB passwords.

**Reconcile:** `GCP/backend-staging` and `main` still diverge (unique commits on both sides). Merge `main` into staging in a pairing session before treating testing as a production release candidate. Do not fast-forward `main` with the full staging delta.

Saige production (`deploy-saige.yml`) must not deploy on a raw `saige/**` push to `main` until `PROD_SAIGE_DEPLOY_ENABLED=true` and Environment `production` reviewers exist.
