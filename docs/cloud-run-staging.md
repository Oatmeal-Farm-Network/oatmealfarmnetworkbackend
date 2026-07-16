# Cloud Run Staging Services

**Task branch:** `task/cicd-cloud-run-staging`
**Owner:** Aryan
**GCP Project:** `oatmeal-farm-staging`
**Region:** `us-central1`
**Last updated:** July 2026

---

## Service URLs

| Service | URL |
|---|---|
| Backend  | https://oatmeal-backend-staging-1087130530284.us-central1.run.app |
| Frontend | https://oatmeal-frontend-staging-1087130530284.us-central1.run.app |
| Saige    | *(pending — Sankeerth / `oatmeal-saige-staging`)* |

---

## Deployment Status

### Backend (`oatmeal-backend-staging`)

- [x] Service created and reachable
- [x] Runtime SA: `stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com` (RO→prod SQL)
- [x] Cloud SQL Auth Proxy: `animated-flare-421518:us-central1:oatmealailive`
- [x] Secrets mounted: `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY`
- [x] `min-instances: 1`
- [ ] Final deploy using the real application image from Artifact Registry
  - Image URI: `us-central1-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:<COMMIT_SHA>`
  - May still be on placeholder `hello` image until CD / manual real-image deploy

See [STAGING_CLOUD_SQL_SETUP.md](./staging/STAGING_CLOUD_SQL_SETUP.md).

### Frontend (`oatmeal-frontend-staging`)

- [x] Service created and reachable
- [ ] Attach `frontend-sa@oatmeal-farm-staging.iam.gserviceaccount.com`
- [ ] Final frontend image / config (out of scope for backend-only CD this sprint)

### Saige (`oatmeal-saige-staging`)

- [ ] Service not created yet — **Sankeerth Part A**
- [ ] `min-instances: 1`, memory `2Gi`, CPU `2`
- [ ] Attach `saige-sa` (+ Saige API secrets)
- [ ] Document staging URL

---

## Commands Used (initial placeholder deploy)

```bash
gcloud run deploy oatmeal-backend-staging \
  --image us-docker.pkg.dev/cloudrun/container/hello \
  --project oatmeal-farm-staging \
  --region us-central1 \
  --allow-unauthenticated

gcloud run deploy oatmeal-frontend-staging \
  --image us-docker.pkg.dev/cloudrun/container/hello \
  --project oatmeal-farm-staging \
  --region us-central1 \
  --allow-unauthenticated
```

---

## Notes

- Region `us-central1` aligns with Artifact Registry (David).
- Backend DB secrets are **done** (not blocked on Sankeerth). Sankeerth owns Saige service + Saige AI secrets only.
- PR: `task/cicd-cloud-run-staging` → `epic/backend-reorg` (merged).
