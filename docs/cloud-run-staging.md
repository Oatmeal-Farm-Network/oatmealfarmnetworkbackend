# Cloud Run Staging Services

**Task branch:** `task/cicd-cloud-run-staging`
**Owner:** Aryan
**GCP Project:** `oatmeal-farm-staging`
**Region:** `us-central1`
**Last updated:** July 9, 2026

---

## Service URLs

| Service | URL |
|---|---|
| Backend  | https://oatmeal-backend-staging-1087130530284.us-central1.run.app |
| Frontend | https://oatmeal-frontend-staging-1087130530284.us-central1.run.app |

---

## Deployment Status

Both services are currently running the **placeholder `hello` image** (`us-docker.pkg.dev/cloudrun/container/hello`), deployed to confirm the Cloud Run services boot and respond correctly in the staging project. This is a verification step, not the final production-ready configuration.

- [x] `oatmeal-backend-staging` deployed and reachable
- [x] `oatmeal-frontend-staging` deployed and reachable
- [ ] Real service accounts attached (`backend-sa`, `frontend-sa`) — blocked on Bringesh (IAM task)
- [ ] Secret Manager env vars wired in (`DATABASE_URL`, `SECRET_KEY`, etc.) — blocked on Sankeerth (secrets task), pending final secret names
- [ ] Final deploy using the real application image from Artifact Registry
  - Image URI format: `us-central1-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:<COMMIT_SHA>`
- [ ] `min-instances: 1` and final memory/CPU limits applied
- [ ] PR opened: `task/cicd-cloud-run-staging` → `epic/backend-reorg`

---

## Commands Used

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

- Region `us-central1` confirmed to align with Artifact Registry setup (David's task).
- Once service accounts and secrets are available from Bringesh and Sankeerth, both services will be redeployed with the real backend image and updated config, and this doc will be revised accordingly.