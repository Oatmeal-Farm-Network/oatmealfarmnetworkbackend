# 🌾 Oatmeal Farm Network — CI/CD Task Assignments

> **Scope:** CI/CD & Environment Strategy (Staging Only)
> **Date:** July 4, 2026
> **Sprint Focus:** Staging environment setup and GitHub Actions pipeline
>
> ---
>
> ⚠️ **IMPORTANT — READ BEFORE STARTING:**
> **Do NOT touch any production services.** All work is scoped to the `oatmeal-farm-staging` GCP project only.
> Production deployments are on hold until Staging is fully validated. When in doubt, ask in the team channel first.

---

## 🌿 Git Workflow — Every Team Member Must Follow This

Before starting any work, **pull the latest epic branch** that all CI/CD tasks branch off from:

```bash
# 1. Clone the repo (if you haven't already)
git clone <repo-url>
cd oatmealfarmnetworkbackend

# 2. Fetch all remote branches
git fetch --all

# 3. Switch to the epic base branch and pull the latest
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
```

> ⚠️ **All individual task branches must be created from** `epic/backend-reorg`**, NOT from** `main`**.**
> When your work is done, open a PR targeting `epic/backend-reorg` — not `main`.

---



## 👥 Team Overview


| Member        | Area of Responsibility                              | Branch Name                           |
| ------------- | --------------------------------------------------- | ------------------------------------- |
| **Vidyanand** | GCP Staging Project Setup & Cloud SQL               | `task/cicd-gcp-staging-cloudsql`      |
| **David**     | Artifact Registry & Docker Configuration            | `task/cicd-artifact-registry-docker`  |
| **Aryan**     | Cloud Run: Frontend & Backend Staging Services      | `task/cicd-cloud-run-staging`         |
| **Sankeerth** | Cloud Run: Saige AI Service + Secret Manager Config | `task/cicd-cloud-run-saige-secrets`   |
| **Navdeep**   | GitHub Actions — CI Pipeline (Phase 1)              | `task/cicd-github-actions-ci`         |
| **Guia**      | GitHub Actions — Staging Deployment (Phase 2)       | `task/cicd-github-actions-cd-staging` |
| **Bringesh**  | IAM & Cross-Project Access Configuration            | `task/cicd-iam-service-accounts`      |


---



## 📋 Individual Task Assignments

---



### 🟦 Vidyanand — GCP Staging Project Setup & Cloud SQL

**Goal:** Provision and configure the staging GCP project and its database.

#### 🔀 Git Setup — Run These First

```bash
# Pull the latest epic base branch
git checkout epic/backend-reorg
git pull origin epic/backend-reorg

# Create and switch to your task branch
git checkout -b task/cicd-gcp-staging-cloudsql

# When your work is done, push the branch
git push -u origin task/cicd-gcp-staging-cloudsql
```

> Then open a **Pull Request** on GitHub: `task/cicd-gcp-staging-cloudsql` → `epic/backend-reorg`



#### ✅ Tasks

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

#### 🔀 Git Setup — Run These First

```bash
# Pull the latest epic base branch
git checkout epic/backend-reorg
git pull origin epic/backend-reorg

# Create and switch to your task branch
git checkout -b task/cicd-artifact-registry-docker

# When your work is done, stage, commit, and push
git add -A
git commit -m "feat: configure Artifact Registry and update Dockerfile for server_all.py"
git push -u origin task/cicd-artifact-registry-docker
```

> Then open a **Pull Request** on GitHub: `task/cicd-artifact-registry-docker` → `epic/backend-reorg`



#### ✅ Tasks

- [ ] Create an **Artifact Registry** repository (Docker format) in the `oatmeal-farm-staging` project
  - Suggested name: `oatmeal-farm-registry`
  - Region: choose and document the region (align with Cloud Run region)
- [ ] Review and update the project `Dockerfile` to build the unified `server_all.py` entry point
  - Ensure both `app/` and `saige/` dependencies are included
  - Optimize layer caching (e.g., separate `pip install` step before copying source code)
- [ ] Confirm the image builds locally with `docker build` and boots cleanly:
  ```bash
  docker build -t oatmeal-backend:test .
  docker run --rm oatmeal-backend:test
  ```
- [ ] Document the full image URI format to be used by the pipeline:
  ```
  REGION-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:<COMMIT_SHA>
  ```
- [ ] Ensure **no** `:latest` **tag** is ever pushed — enforce commit SHA tagging only

> ⚠️ **Coordinate with Navdeep & Guia** — they will use the image URI format you define in the GitHub Actions workflows.

---



### 🟨 Aryan — Cloud Run: Frontend & Backend Staging Services

**Goal:** Create and configure the Frontend and Backend Cloud Run services in the staging project.

#### 🔀 Git Setup — Run These First

```bash
# Pull the latest epic base branch
git checkout epic/backend-reorg
git pull origin epic/backend-reorg

# Create and switch to your task branch
git checkout -b task/cicd-cloud-run-staging

# When your work is done, stage, commit, and push
git add -A
git commit -m "feat: configure Cloud Run staging services for frontend and backend"
git push -u origin task/cicd-cloud-run-staging
```

> Then open a **Pull Request** on GitHub: `task/cicd-cloud-run-staging` → `epic/backend-reorg`



#### ✅ Tasks

- [ ] Create the following **Cloud Run services** in `oatmeal-farm-staging`:
  - `oatmeal-frontend-staging`
  - `oatmeal-backend-staging` (modular monolith: accounts, directory, marketplaces, services, e-commerce, newsroom, agents, etc.)
- [ ] Configure each service with:
  - `min-instances: 1` (to avoid cold starts)
  - Appropriate memory and CPU limits
  - Environment variable references from Secret Manager (coordinate with **Sankeerth** for the secret names)
- [ ] Attach the correct service account to each Cloud Run service (get emails from **Bringesh**):
  ```bash
  gcloud run services update oatmeal-backend-staging \
    --service-account=backend-sa@oatmeal-farm-staging.iam.gserviceaccount.com \
    --project=oatmeal-farm-staging \
    --region=REGION

  gcloud run services update oatmeal-frontend-staging \
    --service-account=frontend-sa@oatmeal-farm-staging.iam.gserviceaccount.com \
    --project=oatmeal-farm-staging \
    --region=REGION
  ```
- [ ] Do an initial manual deploy of a placeholder image to verify both services start correctly:
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
- [ ] Document each service's staging URL and share with the team

> ⚠️ **Do NOT configure or touch any Production Cloud Run services.** Staging only for now.
> ⚠️ **Wait for Bringesh** to create the service accounts before attaching them.
> ⚠️ **Coordinate with Sankeerth** on env variable / secret references before final deploy.

---



### 🟧 Sankeerth — Cloud Run: Saige AI Service + Secret Manager Configuration

**Goal:** Deploy the Saige AI Advisor Cloud Run service and wire all environment secrets across the staging environment.

#### 🔀 Git Setup — Run These First

```bash
# Pull the latest epic base branch
git checkout epic/backend-reorg
git pull origin epic/backend-reorg

# Create and switch to your task branch
git checkout -b task/cicd-cloud-run-saige-secrets

# When your work is done (e.g., after adding any config/docs files), push
git add -A
git commit -m "feat: configure Saige Cloud Run service and Secret Manager env wiring"
git push -u origin task/cicd-cloud-run-saige-secrets
```

> Then open a **Pull Request** on GitHub: `task/cicd-cloud-run-saige-secrets` → `epic/backend-reorg`



#### ✅ Tasks

**Part A — Saige Cloud Run Service**

- [ ] Create the `oatmeal-saige-staging` Cloud Run service in `oatmeal-farm-staging`:
  ```bash
  gcloud run deploy oatmeal-saige-staging \
    --image us-docker.pkg.dev/cloudrun/container/hello \
    --project oatmeal-farm-staging \
    --region us-central1 \
    --allow-unauthenticated
  ```
- [ ] Configure Saige-specific settings:
  - `min-instances: 1` — **mandatory** for Saige to avoid AI model cold starts
  - Increase memory: `--memory 2Gi` (or higher depending on model size)
  - Increase CPU: `--cpu 2`
- [ ] Attach the Saige service account (get email from **Bringesh**):
  ```bash
  gcloud run services update oatmeal-saige-staging \
    --service-account=saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com \
    --project=oatmeal-farm-staging \
    --region=REGION
  ```
- [ ] Document the Saige staging URL and share with the team

**Part B — Secret Manager: Environment Variable Wiring**

- [ ] Create all required secrets in GCP Secret Manager for the staging project:
  ```bash
  # Example — repeat for each required secret
  echo -n "<secret-value>" | gcloud secrets create DATABASE_URL \
    --data-file=- \
    --project=oatmeal-farm-staging
  ```
  Secrets to create (coordinate with Vidyanand for DB values):
  - `DATABASE_URL` — staging Cloud SQL connection string
  - `SECRET_KEY` — app secret key
  - Any API keys needed by Saige (AI provider keys, etc.)
- [ ] Grant each Cloud Run service account access to the secrets it needs:
  ```bash
  gcloud secrets add-iam-policy-binding DATABASE_URL \
    --project=oatmeal-farm-staging \
    --member="serviceAccount:backend-sa@oatmeal-farm-staging.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
  ```
- [ ] Verify secrets are mounted correctly in Cloud Run by checking service env config:
  ```bash
  gcloud run services describe oatmeal-backend-staging \
    --project=oatmeal-farm-staging \
    --region=REGION \
    --format="yaml"
  ```
- [ ] Document the full list of secret names and which services consume them — share with Aryan and Guia

> ⚠️ **Do NOT create or modify any secrets in the Production GCP project.** Staging only.
> ⚠️ **Wait for Bringesh** to create service accounts before granting secret access.
> ⚠️ **Wait for Vidyanand** to provision Cloud SQL before storing the `DATABASE_URL` secret.

---



### 🟥 Navdeep — GitHub Actions: CI Pipeline (Phase 1)

**Goal:** Build the CI gate that runs on every Pull Request to `main`.

#### 🔀 Git Setup — Run These First

```bash
# Pull the latest epic base branch
git checkout epic/backend-reorg
git pull origin epic/backend-reorg

# Create and switch to your task branch
git checkout -b task/cicd-github-actions-ci

# After creating the workflow file, stage, commit, and push
git add .github/workflows/ci.yml
git commit -m "feat: add GitHub Actions CI workflow (lint + boot check)"
git push -u origin task/cicd-github-actions-ci
```

> Then open a **Pull Request** on GitHub: `task/cicd-github-actions-ci` → `epic/backend-reorg`



#### ✅ Tasks

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

#### 🔀 Git Setup — Run These First

```bash
# Pull the latest epic base branch
git checkout epic/backend-reorg
git pull origin epic/backend-reorg

# Create and switch to your task branch
git checkout -b task/cicd-github-actions-cd-staging

# After creating the workflow file, stage, commit, and push
git add .github/workflows/deploy-staging.yml
git commit -m "feat: add GitHub Actions CD workflow for staging deployment"
git push -u origin task/cicd-github-actions-cd-staging
```

> Then open a **Pull Request** on GitHub: `task/cicd-github-actions-cd-staging` → `epic/backend-reorg`



#### ✅ Tasks

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
    ```bash
     docker build -t REGION-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:$COMMIT_SHA .
    ```
  4. **Push** image to Artifact Registry (no `:latest` tag):
    ```bash
     docker push REGION-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:$COMMIT_SHA
    ```
  5. **Deploy** to the staging Cloud Run service (`oatmeal-backend-staging`) using the commit SHA image:
    ```bash
     gcloud run deploy oatmeal-backend-staging \
       --image REGION-docker.pkg.dev/oatmeal-farm-staging/oatmeal-farm-registry/backend:$COMMIT_SHA \
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

#### 🔀 Git Setup — Run These First

```bash
# Pull the latest epic base branch
git checkout epic/backend-reorg
git pull origin epic/backend-reorg

# Create and switch to your task branch
git checkout -b task/cicd-iam-service-accounts

# After documenting IAM setup (e.g., adding a docs/iam-setup.md file), push
git add -A
git commit -m "docs: add IAM service account setup and cross-project access notes"
git push -u origin task/cicd-iam-service-accounts
```

> Then open a **Pull Request** on GitHub: `task/cicd-iam-service-accounts` → `epic/backend-reorg`



#### ✅ Tasks

- [x] Create a dedicated **GitHub Actions service account** in `oatmeal-farm-staging`:
  - Name suggestion: `github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com`
  - Roles needed:
    ```bash
    gcloud projects add-iam-policy-binding oatmeal-farm-staging \
      --member="serviceAccount:github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com" \
      --role="roles/artifactregistry.writer"

    gcloud projects add-iam-policy-binding oatmeal-farm-staging \
      --member="serviceAccount:github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com" \
      --role="roles/run.admin"

    gcloud projects add-iam-policy-binding oatmeal-farm-staging \
      --member="serviceAccount:github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com" \
      --role="roles/iam.serviceAccountUser"
    ```
- [x] Create dedicated **Cloud Run service accounts** for each staging service (Backend, Frontend, Saige):
  ```bash
  gcloud iam service-accounts create backend-sa --project=oatmeal-farm-staging
  gcloud iam service-accounts create frontend-sa --project=oatmeal-farm-staging
  gcloud iam service-accounts create saige-sa --project=oatmeal-farm-staging
  ```
  - Grant each `roles/cloudsql.client` and `roles/secretmanager.secretAccessor`
- [x] Set up **GitHub Actions authentication**:
  - Preferred: Workload Identity Federation (keyless) — generate the provider and client ID
  - Alternative: Download a JSON key and store it as a GitHub Actions secret (`GCP_SA_KEY`)
  - Document which method was used and **share the secret name with Guia**
- [ ] Apply the **cross-project IAM rule** (Shared Registry strategy):
  ```bash
  # Grant the Production Cloud Run SA read access to the staging Artifact Registry
  gcloud artifacts repositories add-iam-policy-binding oatmeal-farm-registry \
    --location=REGION \
    --project=oatmeal-farm-staging \
    --member="serviceAccount:<PROD-CLOUD-RUN-SA>@<PROD-PROJECT>.iam.gserviceaccount.com" \
    --role="roles/artifactregistry.reader"
  ```
  - Get the production SA email from John first
  - ⚠️ This is a one-time config step — do NOT modify production services themselves
- [ ] Document all service account emails and their roles in a shared internal doc

> ⚠️ **You are the blocker for Aryan, Guia, and Vidyanand.** Prioritize getting service accounts created and communicating credentials to the team ASAP.

---



## 🔗 Dependency & Coordination Map

```
epic/backend-reorg  ◄── ALL branches start from here
    │
    ├── task/cicd-iam-service-accounts              (Bringesh)   ◄── START FIRST
    │       │
    │       ├──► task/cicd-cloud-run-staging        (Aryan)
    │       ├──► task/cicd-cloud-run-saige-secrets  (Sankeerth)
    │       ├──► task/cicd-github-actions-cd-staging (Guia)
    │       └──► task/cicd-gcp-staging-cloudsql     (Vidyanand)
    │
    ├── task/cicd-artifact-registry-docker          (David)      ◄── Can start in parallel
    │       │
    │       ├──► task/cicd-github-actions-ci        (Navdeep)
    │       └──► task/cicd-github-actions-cd-staging (Guia)
    │
    ├── task/cicd-gcp-staging-cloudsql              (Vidyanand)
    │       │
    │       ├──► task/cicd-cloud-run-staging        (Aryan)
    │       └──► task/cicd-cloud-run-saige-secrets  (Sankeerth)  ◄── needs DB URL
    │
    └── task/cicd-cloud-run-saige-secrets           (Sankeerth)
            │
            └──► task/cicd-cloud-run-staging        (Aryan)      ◄── needs secret names
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
- [ ] All task branches have been merged into `epic/backend-reorg` via reviewed PRs

---



## 🚫 Out of Scope (This Sprint)

- ❌ Any changes to the **Production** GCP project (`oatmeal AI`)
- ❌ Setting up or running the `pytest` suite
- ❌ Phase 3 Production deployment workflow (GitHub Release trigger)
- ❌ Frontend CI/CD pipeline (backend monolith only for now)

---

*Last updated: July 4, 2026 | Maintained by team lead — Sankeerth added to sprint*