# 🌾 Oatmeal Farm Network — CI/CD Task Assignments

> **Scope:** CI/CD & Environment Strategy (Staging Only)
> **Date:** July 4, 2026
> **Sprint Focus:** Staging environment setup and GitHub Actions pipeline
>
> ---
> ⚠️ **IMPORTANT — READ BEFORE STARTING:**
> **Do NOT touch any production services.** All work is scoped to the `oatmeal-farm-staging` GCP project only.
> Production deployments are on hold until Staging is fully validated. When in doubt, ask in the team channel first.

---

## 👥 Team Overview

| Member | Area of Responsibility |
|---|---|
| **Vidyanand** | GCP Staging Project Setup & Cloud SQL |
| **David** | Artifact Registry & Docker Configuration |
| **Aryan** | Cloud Run Services (Staging) |
| **Navdeep** | GitHub Actions — CI Pipeline (Phase 1) |
| **Guia** | GitHub Actions — Staging Deployment (Phase 2) |
| **Bringesh** | IAM & Cross-Project Access Configuration |

---

## 📋 Individual Task Assignments

---

### 🟦 Vidyanand — GCP Staging Project Setup & Cloud SQL

**Goal:** Provision and configure the staging GCP project and its database.

- [ ] Create (or confirm) the `oatmeal-farm-staging` GCP project exists and billing is enabled
- [ ] Enable required GCP APIs: Cloud Run, Cloud SQL, Artifact Registry, IAM, Secret Manager
- [ ] Provision a **Cloud SQL** instance (PostgreSQL) in the staging project
  - Use dummy / anonymized data only — no real user data
- [ ] Create a dedicated database and user for the staging backend
- [ ] Document the staging Cloud SQL connection string and share credentials securely via Secret Manager
- [ ] Verify the database is accessible only within the staging project's VPC / service account scope

> ⚠️ **Wait for Bringesh** to finalize IAM service accounts before locking down access rules.

---

### 🟩 David — Artifact Registry & Docker Configuration

**Goal:** Set up the single Docker image registry and ensure the Dockerfile is production-quality.

- [ ] Create an **Artifact Registry** repository (Docker format) in the `oatmeal-farm-staging` project
  - Suggested name: `oatmeal-farm-registry`
  - Region: choose and document the region (align with Cloud Run region)
- [ ] Review and update the project `Dockerfile` to build the unified `server_all.py` entry point
  - Ensure both `app/` and `saige/` dependencies are included
  - Optimize layer caching (e.g., separate `pip install` step before copying source code)
- [ ] Confirm the image builds locally with `docker build` and boots cleanly
- [ ] Document the full image URI format to be used by the pipeline:
  ```
  REGION-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:<COMMIT_SHA>
  ```
- [ ] Ensure **no `:latest` tag** is ever pushed — enforce commit SHA tagging only

> ⚠️ **Coordinate with Navdeep & Guia** — they will use the image URI format you define in the GitHub Actions workflows.

---

### 🟨 Aryan — Cloud Run Services (Staging)

**Goal:** Create and configure the three Cloud Run services in the staging project.

- [ ] Create the following **Cloud Run services** in `oatmeal-farm-staging`:
  - `oatmeal-frontend-staging`
  - `oatmeal-backend-staging` (modular monolith: accounts, directory, marketplaces, services, e-commerce, newsroom, agents, etc.)
  - `oatmeal-saige-staging` (AI Advisor)
- [ ] Configure each service with:
  - `min-instances: 1` (to avoid cold starts, especially for Saige which has AI dependencies)
  - Appropriate memory and CPU limits
  - Environment variables / Secret Manager references (coordinate with Vidyanand for DB connection strings)
- [ ] Set the service account for each Cloud Run service (coordinate with Bringesh)
- [ ] Do an initial manual deploy of a placeholder or test image to verify services start correctly
- [ ] Document each service's staging URL and share with the team

> ⚠️ **Do NOT configure or touch any Production Cloud Run services.** Staging only for now.
> ⚠️ **Wait for Bringesh** to create the service accounts before attaching them to Cloud Run.

---

### 🟥 Navdeep — GitHub Actions: CI Pipeline (Phase 1)

**Goal:** Build the CI gate that runs on every Pull Request to `main`.

- [ ] Create the workflow file: `.github/workflows/ci.yml`
- [ ] Configure trigger:
  ```yaml
  on:
    pull_request:
      branches: [main]
  ```
- [ ] Add the following CI jobs:
  - **Lint:** Run `ruff` (or `flake8`) on both `app/` and `saige/`
  - **Boot Check:** Run a verification script to ensure `server_all.py` starts without import conflicts
    - Example: `python server_all.py &` + health check curl after a short sleep, then kill
- [ ] Ensure the workflow fails the PR if any job fails (block merging on failure)
- [ ] Test the workflow by opening a draft PR and verifying all checks appear in GitHub

> ⚠️ **Note:** Per scope, the `pytest` suite is **excluded** from this sprint. Leave a `# TODO: add pytest step` placeholder comment.
> ⚠️ **Coordinate with David** for the correct Python version and dependency install steps matching the Dockerfile.

---

### 🟪 Guia — GitHub Actions: Staging Deployment (Phase 2)

**Goal:** Build the CD workflow that auto-deploys to Staging when a PR is merged to `main`.

- [ ] Create the workflow file: `.github/workflows/deploy-staging.yml`
- [ ] Configure trigger:
  ```yaml
  on:
    push:
      branches: [main]
  ```
- [ ] Add the following deployment steps:
  1. **Checkout** code and extract `COMMIT_SHA` (short SHA via `${{ github.sha }}`)
  2. **Authenticate** to GCP using Workload Identity Federation (or Service Account JSON secret — coordinate with Bringesh for the secret name)
  3. **Build & Tag** Docker image:
     ```
     docker build -t REGION-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:$COMMIT_SHA .
     ```
  4. **Push** image to Artifact Registry (no `:latest` tag)
  5. **Deploy** to the staging Cloud Run service (`oatmeal-backend-staging`) using the commit SHA image
     ```
     gcloud run deploy oatmeal-backend-staging \
       --image REGION-docker.pkg.dev/oatmeal-farm-staging/... \
       --project oatmeal-farm-staging \
       --region REGION
     ```
- [ ] Store all sensitive values (project ID, region, image URI prefix) as **GitHub Actions Secrets / Variables**
- [ ] Test end-to-end by merging a small change to `main` and verifying the staging URL reflects the change

> ⚠️ **Staging only.** Do not create or reference a production deployment step in this workflow.
> ⚠️ **Wait for Bringesh** to provide the GCP service account secret / Workload Identity details.
> ⚠️ **Coordinate with David** for the exact Artifact Registry image URI format.

---

### 🟫 Bringesh — IAM & Cross-Project Access Configuration

**Goal:** Set up all service accounts, permissions, and the cross-project Artifact Registry access rule.

- [ ] Create a dedicated **GitHub Actions service account** in `oatmeal-farm-staging`:
  - Name suggestion: `github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com`
  - Roles needed: `Artifact Registry Writer`, `Cloud Run Admin`, `Service Account User`
- [ ] Create dedicated **Cloud Run service accounts** for each staging service (Backend, Frontend, Saige):
  - Grant each the minimum roles needed (e.g., `Cloud SQL Client`, `Secret Manager Secret Accessor`)
- [ ] Set up **GitHub Actions authentication**:
  - Preferred: Workload Identity Federation (keyless) — generate the provider and client ID
  - Alternative: Download a JSON key and store it as a GitHub Actions secret (`GCP_SA_KEY`)
  - Document which method was used and share the secret name with Guia
- [ ] Apply the **cross-project IAM rule** (Shared Registry strategy):
  - In `oatmeal-farm-staging` Artifact Registry, grant the **Production Cloud Run service account** the `Artifact Registry Reader` role
  - Coordinate with Vidyanand / team lead to get the production service account email from John
  - ⚠️ This is a one-time config step — do NOT modify production services themselves
- [ ] Document all service account emails and their roles in a shared internal doc

> ⚠️ **You are the blocker for Aryan, Guia, and Navdeep.** Prioritize getting service accounts created and communicating credentials to the team ASAP.

---

## 🔗 Dependency & Coordination Map

```
Bringesh (IAM)
    │
    ├──► Aryan (Cloud Run — needs service accounts)
    │
    ├──► Guia (CD Workflow — needs GCP auth secret)
    │
    └──► Vidyanand (Cloud SQL — needs SA for DB access)

David (Dockerfile & Registry)
    │
    ├──► Navdeep (CI — needs correct build environment)
    │
    └──► Guia (CD — needs image URI format)

Vidyanand (Cloud SQL)
    │
    └──► Aryan (Cloud Run — needs DB connection string / secret)
```

---

## ✅ Definition of Done (Staging Sprint)

Before this sprint is considered complete, the following must be true:

- [ ] All three staging Cloud Run services are running and reachable via their staging URLs
- [ ] Merging a PR to `main` automatically triggers a new Docker build and deploys to staging
- [ ] Every Docker image is tagged with a unique commit SHA (no `:latest` anywhere)
- [ ] The CI workflow blocks PRs with lint errors or boot failures
- [ ] All secrets are stored in GitHub Actions Secrets or GCP Secret Manager — **no plaintext credentials in code**
- [ ] Cross-project Artifact Registry reader access is configured (for future production promotion)

---

## 🚫 Out of Scope (This Sprint)

- ❌ Any changes to the **Production** GCP project (`oatmeal AI`)
- ❌ Setting up or running the `pytest` suite
- ❌ Phase 3 Production deployment workflow (GitHub Release trigger)
- ❌ Frontend CI/CD pipeline (backend monolith only for now)

---

*Last updated: July 4, 2026 | Maintained by team lead*
