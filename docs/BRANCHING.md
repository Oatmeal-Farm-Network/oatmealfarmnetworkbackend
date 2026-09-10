# Backend — Git train

This repo follows the Oatmeal AI three-environment train. Do not rename these branches.

```text
feature/*  →  PR  →  GCP/backend-staging  →  PR  →  GCP/backend-testing  →  PR  →  main
                         staging Cloud Run              testing Cloud Run              production
```

Allowed PRs only: work → staging; staging → testing; testing → `main`.

`tests/backend-staging`, `Live`, and `live` are not environment branches.

This repo deploys **four Cloud Run services in every environment**.

| Service | Staging (`oatmeal-farm-staging`) | Testing (`oatmeal-farm-staging`) | Production (`animated-flare-421518`) | Workflows |
|---------|----------------------------------|----------------------------------|--------------------------------------|-----------|
| Main API | `oatmeal-backend-staging` | `oatmeal-backend-testing` | `oatmealfarmnewtorkbackend` | `deploy-staging.yml` / `deploy-testing.yml` / `deploy-backend-prod.yml` |
| Saige | `oatmeal-saige-staging` | `oatmeal-saige-testing` | `saige-backend` | `deploy-saige-staging.yml` / `deploy-saige-testing.yml` / `deploy-saige.yml` |
| Livestock API | `oatmeal-livestock-staging` | `oatmeal-livestock-testing` | `livestock-backend-prod` | `deploy-livestock-*.yml` |
| Oatsense API | `oatmeal-oatsense-staging` | `oatmeal-oatsense-testing` | `oatsense-backend-prod` | `deploy-oatsense-*.yml` |

Testing CD stays fail-closed until isolated Cloud SQL / Firestore and `TESTING_*` exist in **`oatmeal-farm-staging`**. Never create testing or staging services in Oatmeal AI.

`oatsense-backend-prod` is the production oatsense API name (does not exist yet; first successful `main` deploy creates it). Livestock prod already exists.

**Reconcile:** `GCP/backend-staging` and `main` still diverge. Merge `main` into staging in a pairing session before treating testing as a production release candidate. Do not fast-forward `main` with the full staging delta.

Do not deploy from `main` into `oatmeal-farm-staging`.
