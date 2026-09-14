# Artifact Registry Configuration

## Repository Details

- **Registry Name:** `oatmeal-farm-registry`
- **Project:** `oatmeal-farm-staging`
- **Region:** `us-central1`
- **Format:** Docker

## Image URI Format

All images must be tagged and pushed using the following format:

```
us-central1-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:<COMMIT_SHA>
```

### URI Components:
- `us-central1-docker.pkg.dev` — Artifact Registry endpoint
- `oatmeal-farm-staging` — GCP Project ID
- `oatmeal-farm-registry` — Registry repository name
- `backend` — Image name
- `<COMMIT_SHA>` — Git commit SHA (e.g., `a1b2c3d4e5f6g7h8`)

## Tagging Rules

✅ **Required:**
- All images MUST be tagged with commit SHA
- Example: `backend:a1b2c3d4`

❌ **Forbidden:**
- Never use `:latest` tag
- Never use vague version tags like `:v1.0`

## Example Usage

### Build image:
```bash
docker build -t oatmeal-backend:test .
```

### Tag for Artifact Registry:
```bash
docker tag oatmeal-backend:test us-central1-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:a1b2c3d4
```

### Push to Artifact Registry:
```bash
docker push us-central1-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:a1b2c3d4
```

### Pull from Cloud Run:
```bash
gcloud run deploy oatmeal-backend-staging \
  --image=us-central1-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:a1b2c3d4 \
  --project=oatmeal-farm-staging \
  --region=us-central1
```

## Dockerfile Entry Point

The Dockerfile runs `server_all.py` (unified backend + Saige AI):

```dockerfile
CMD ["uvicorn", "server_all:app", "--host", "0.0.0.0", "--port", "8080"]
```

This starts both:
- Main backend at `/`
- Saige AI advisor at `/saige/*`

## Prerequisites

- Docker installed and running
- gcloud CLI configured with staging project credentials
- Access to `oatmeal-farm-staging` GCP project
