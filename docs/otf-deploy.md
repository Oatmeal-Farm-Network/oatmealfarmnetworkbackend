# Over the Fence (OTF) Social — staging deploy (livestock-style)

OTF is a **separate Cloud Run service** like livestock (LSA): a thin FastAPI
entrypoint that mounts [`app/routers/mill.py`](../app/routers/mill.py). Logic
stays in `app/`; the service is only packaging + CD.

Local:

```bash
uvicorn otf.api:app --reload --port 8004
```

Health: `GET /health` → `{"status":"ok","service":"otf"}`  
API: `/api/admin/mill/*`

Main backend still mounts `mill` (dual-serve) until frontend cutover.

---

## Staging

| Item | Value |
|------|-------|
| Workflow | `.github/workflows/deploy-otf-staging.yml` |
| Triggers | push to `GCP/backend-staging` (path-filtered) + `workflow_dispatch` |
| Cloud Run | `oatmeal-otf-staging` |
| Image | `.../oatmeal-farm-registry/otf:<sha>` |
| Build | `docker build -f otf/Dockerfile.backend .` (repo root, like livestock) |
| Runtime SA | Same staging DB SA as livestock |

### Path filters

- `otf/**`
- `app/routers/mill.py`
- `app/database.py`, `app/schema_ensure.py`
- `requirements.txt`
- workflow file

### Secrets / vars

Same WIF as livestock. Optional: `STAGING_OTF_FRONTEND_URL` (falls back to
`STAGING_FRONTEND_URL`). Service mounts `DB_*`, `SECRET_KEY`.

### Frontend

`VITE_OTF_API_URL=<oatmeal-otf-staging URL>`

### Production

**Deferred** — staging only for now.
