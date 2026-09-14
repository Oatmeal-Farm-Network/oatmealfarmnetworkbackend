## Hop

<!-- Pick one. Feature PRs may only target staging. -->

- [ ] Feature / fix → `GCP/backend-staging` (staging Cloud Run)
- [ ] `GCP/backend-staging` → `GCP/backend-testing` (testing Cloud Run)
- [ ] `GCP/backend-testing` → `main` (production)

Do **not** open a feature PR into testing or `main`.
Do **not** target `tests/backend-staging` or `Live`.

## Summary

-

## Tickets / services in this promotion

<!-- main API / Saige / livestock / oatsense -->

-

## Checks

- [ ] CI is green (ruff + boot checks)
- [ ] Path filters match the services that should deploy
- [ ] CORS / `FRONTEND_URL` updated if this hop adds a frontend origin (`TESTING_*` / `PROD_*`)
- [ ] Migrations / data notes (or N/A)
- [ ] Testing hop does not use production DB passwords or `SECRET_KEY`

## Testing hop only

- [ ] Staging URL was exercised
- [ ] Isolated testing DB / Firestore is in use
- [ ] QA / product sign-off on the testing environment (name + date):

## Production hop only

- [ ] Testing URL was signed off
- [ ] GitHub Environment `production` approval required
- [ ] `PROD_*` / `PROD_SAIGE_DEPLOY_ENABLED` are intentionally set
