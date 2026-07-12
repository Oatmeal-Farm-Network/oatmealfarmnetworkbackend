# Cloud Run Staging Services

**Owner:** Bringesh / team  
**GCP Project:** `oatmeal-farm-staging`  
**Region:** `us-central1`  
**Last updated:** July 2026

---

## Service URLs

| Service | URL |
|---|---|
| Backend  | https://oatmeal-backend-staging-1087130530284.us-central1.run.app |
| Frontend | https://oatmeal-frontend-staging-1087130530284.us-central1.run.app |
| Saige    | Separate service / CD — see [staging/SAIGE_STAGING_SETUP.md](./staging/SAIGE_STAGING_SETUP.md) |

---

## Deployment Status

### Backend (`oatmeal-backend-staging`)

- [x] Service created and reachable
- [x] Real app image from Artifact Registry via CD (`GCP/backend-staging`)
- [x] Workflow: `.github/workflows/deploy-staging.yml`
- [x] Process: **`uvicorn app.main:app`** (backend only — not `server_all` / Saige)
- [x] Runtime SA: `stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com`
- [x] DB: Cloud SQL Python Connector → prod `oatmealailive` (RO)
- [x] Env: `INSTANCE_CONNECTION_NAME`, `SKIP_SCHEMA_ENSURE=true`
- [x] Secrets: `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY`
- [x] `min-instances: 1`

**Operator guide:** [staging/BACKEND_STAGING_DEPLOY.md](./staging/BACKEND_STAGING_DEPLOY.md)  
**DB design:** [staging/STAGING_CLOUD_SQL_SETUP.md](./staging/STAGING_CLOUD_SQL_SETUP.md)

### Frontend (`oatmeal-frontend-staging`)

- [x] Service created and reachable
- [ ] Attach `frontend-sa@oatmeal-farm-staging.iam.gserviceaccount.com`
- [ ] Final frontend image / config (out of scope for backend-only CD this sprint)

### Saige (`oatmeal-saige-staging`)

- Separate CI/CD on branch **`GCP/saige-staging`** — workflow `.github/workflows/deploy-saige.yml`
- **Not** loaded by the backend staging image command
- See [staging/SAIGE_STAGING_DEPLOY.md](./staging/SAIGE_STAGING_DEPLOY.md) and [staging/SAIGE_STAGING_SETUP.md](./staging/SAIGE_STAGING_SETUP.md)

---

## Notes

- Region `us-central1` aligns with Artifact Registry.
- Backend staging CD must not require Saige LLM secrets (`GOOGLE_API_KEY` / Vertex).
- Cloud Shell may print a harmless `Gaia id not found` warning; commands can still succeed.
