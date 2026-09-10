# Backend — Git train

This repo follows the Oatmeal AI three-environment train. Do not rename these branches.

```text
feature/*  →  PR  →  GCP/backend-staging  →  PR  →  GCP/backend-testing  →  PR  →  main
                         staging Cloud Run              testing Cloud Run              production
```

Allowed PRs only: work → staging; staging → testing; testing → `main`.

`tests/backend-staging`, `Live`, and `live` are not environment branches.

Testing CD stays fail-closed until isolated Cloud SQL / Firestore and `TESTING_*` exist.

**Reconcile:** `GCP/backend-staging` and `main` still diverge. Merge `main` into staging in a pairing session before treating testing as a production release candidate. Do not fast-forward `main` with the full staging delta.

Saige production (`deploy-saige.yml`) is gated by `PROD_SAIGE_DEPLOY_ENABLED` and Environment `production`.
