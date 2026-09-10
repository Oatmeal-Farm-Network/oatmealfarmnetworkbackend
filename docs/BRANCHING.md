# Backend — Git train

This repo follows the Oatmeal AI three-environment train. Do not rename these branches.

```text
feature/*  →  PR  →  GCP/backend-staging  →  PR  →  GCP/backend-testing  →  PR  →  main
                         staging Cloud Run              testing Cloud Run              production
```

Allowed PRs only: work → staging; staging → testing; testing → `main`.

`tests/backend-staging`, `Live`, and `live` are not environment branches.

Testing CD stays fail-closed until isolated Cloud SQL / Firestore and `TESTING_*` exist in **`oatmeal-farm-staging`**. Never create testing or staging services in `animated-flare-421518`.

**Reconcile:** `GCP/backend-staging` and `main` still diverge. Merge `main` into staging in a pairing session before treating testing as a production release candidate. Do not fast-forward `main` with the full staging delta.

### Official production Cloud Run (`animated-flare-421518` / Oatmeal AI)

| Surface | Service | Workflow |
|---------|---------|----------|
| Shared API | `oatmealfarmnewtorkbackend` (typo is the real name) | `deploy-backend-prod.yml` |
| Saige | `saige-backend` | `deploy-saige.yml` (gated by `PROD_SAIGE_DEPLOY_ENABLED` — do **not** set it yet) |

Do not deploy from `main` into `oatmeal-farm-staging`. Staging/testing Saige are `oatmeal-saige-staging` / `oatmeal-saige-testing` in the staging project only.

`deploy-livestock-prod.yml` (`oatmeal-livestock-prod`) and `deploy-oatsense-prod.yml` (`oatmeal-oatsense`) are **not** official prod surfaces — keep them fail-closed. Official LOA/Oatsense frontends live in their own repos.
