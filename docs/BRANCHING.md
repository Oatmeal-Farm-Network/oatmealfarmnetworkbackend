# Branching train

**Train:** `feature/* → GCP/*-development → GCP/*-staging → main`

| Branch | Role |
|--------|------|
| `feature/*` | Work in progress |
| `GCP/*-development` | Development (land features here first) |
| `GCP/*-staging` | QA / UAT / pre-prod only (from development) |
| `main` | Production (from staging only) |

## Rules

- Do **not** open feature PRs into staging or main.
- Staging accepts PRs **only** from `GCP/*-development`.
- Main accepts PRs **only** from `GCP/*-staging`.
- `GCP/*-testing` is **retired** — use development instead. Existing testing branches/services remain for a grace period; new PRs to testing are blocked by `train-direction`.

## Deploys

- Push to `GCP/*-development` → `*-development` Cloud Run (`oatmeal-farm-staging`)
- Push to `GCP/*-staging` → `*-staging` Cloud Run
- Push to `main` → production Cloud Run (`animated-flare-421518`) via GitHub Actions (not Cloud Build)

Updated: 2026-09-15 UTC
