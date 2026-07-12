# IAM Setup — Staging (`oatmeal-farm-staging`)

> **Scope:** Staging environment only. Do not modify production GCP resources.
>
> **Owner:** Bringesh (`task/cicd-iam-service-accounts`)
>
> **Last updated:** July 2026

This document describes the IAM service accounts, roles, and GitHub Actions authentication configured for the staging CI/CD sprint. 

---

## GCP Project


| Setting     | Value                                                                                                               |
| ----------- | ------------------------------------------------------------------------------------------------------------------- |
| Project ID  | `oatmeal-farm-staging`                                                                                              |
| GitHub repo | [Oatmeal-Farm-Network/oatmealfarmnetworkbackend](https://github.com/Oatmeal-Farm-Network/oatmealfarmnetworkbackend) |


---



## Service Accounts



### GitHub Actions (CI/CD deploy)


| Field   | Value                                                               |
| ------- | ------------------------------------------------------------------- |
| Email   | `github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com`  |
| Purpose | Build/push Docker images and deploy to Cloud Run via GitHub Actions |


**Project-level roles:**


| Role                            | Why                                                      |
| ------------------------------- | -------------------------------------------------------- |
| `roles/artifactregistry.writer` | Push images to Artifact Registry                         |
| `roles/run.admin`               | Deploy and update Cloud Run services                     |
| `roles/iam.serviceAccountUser`  | Attach Cloud Run runtime service accounts at deploy time |




### Cloud Run runtime service accounts

Each staging Cloud Run service runs under its own service account.


| Service account                                            | Cloud Run service          | Purpose                  |
| ---------------------------------------------------------- | -------------------------- | ------------------------ |
| `backend-sa@oatmeal-farm-staging.iam.gserviceaccount.com`  | `oatmeal-backend-staging`  | Backend modular monolith |
| `frontend-sa@oatmeal-farm-staging.iam.gserviceaccount.com` | `oatmeal-frontend-staging` | Frontend                 |
| `saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com`    | `oatmeal-saige-staging`    | Saige AI service         |


**Project-level roles (granted to all three):**


| Role                                 | Why                                                              |
| ------------------------------------ | ---------------------------------------------------------------- |
| `roles/cloudsql.client`              | Connect to Cloud SQL (Auth Proxy / IAM DB auth)                  |
| `roles/secretmanager.secretAccessor` | Read secrets from Secret Manager (e.g. `DB_*`, API keys) |


> **Note:** For staging DB access today, prefer the dedicated RO SA below (not `backend-sa` alone). `roles/cloudsql.client` on staging is not enough to reach prod SQL Server.

### Staging → prod DB (read-only)

| Field | Value |
|-------|--------|
| Email | `stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com` |
| Used by | `oatmeal-backend-staging` (DB access via Auth Proxy) |
| Prod project | `animated-flare-421518` |
| Prod role | `roles/cloudsql.client` |
| SQL | `Oatmealailivedb` / `db_datareader` only |
| Connection name | `animated-flare-421518:us-central1:oatmealailive` |

See [STAGING_CLOUD_SQL_SETUP.md](./staging/STAGING_CLOUD_SQL_SETUP.md).

---



## GitHub Actions Authentication

**Method:** Workload Identity Federation (keyless) — no JSON service account key stored in GitHub.

### Workload Identity Pool & Provider


| Resource           | Name                                             |
| ------------------ | ------------------------------------------------ |
| Pool               | `github-pool`                                    |
| OIDC provider      | `github-provider`                                |
| Issuer             | `https://token.actions.githubusercontent.com`    |
| Allowed repository | `Oatmeal-Farm-Network/oatmealfarmnetworkbackend` |


**Full provider path** (used in workflows):

```text
projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-pool/providers/github-provider
```

Replace `<PROJECT_NUMBER>` with the staging project number:

```bash
gcloud projects describe oatmeal-farm-staging --format="value(projectNumber)"
```

The GitHub Actions SA has `roles/iam.workloadIdentityUser` bound to principals from this pool for the repo above.

### GitHub repository secrets

Configure these in **GitHub → Settings → Secrets and variables → Actions** on `oatmealfarmnetworkbackend`:


| Secret name                              | Value                                                              |
| ---------------------------------------- | ------------------------------------------------------------------ |
| `STAGING_GCP_WORKLOAD_IDENTITY_PROVIDER` | Full provider path (see above) — **must match** `deploy-staging.yml` |
| `STAGING_GCP_SERVICE_ACCOUNT`            | `github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com` |
| `STAGING_GCP_PROJECT_ID`                 | `oatmeal-farm-staging`                                             |


Do **not** commit secret values to this repo.

### Workflow usage (for Guia)

```yaml
permissions:
  contents: read
  id-token: write   # required for OIDC

steps:
  - uses: actions/checkout@v4

  - name: Authenticate to Google Cloud (Staging)
    uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: ${{ secrets.STAGING_GCP_WORKLOAD_IDENTITY_PROVIDER }}
      service_account: ${{ secrets.STAGING_GCP_SERVICE_ACCOUNT }}

  - uses: google-github-actions/setup-gcloud@v2

env:
  PROJECT_ID: ${{ secrets.STAGING_GCP_PROJECT_ID }}
```

> Staging CD triggers on pushes to branch `GCP/backend-staging` (see `.github/workflows/deploy-staging.yml`).

---



## Cross-Project Artifact Registry Access

**Status: Deferred** — pending team decision on production environment setup.

When production is finalized:

1. Get the production Cloud Run service account email from John.
2. Grant it read access to the staging Artifact Registry (IAM binding only — do not modify production services):

```bash
gcloud artifacts repositories add-iam-policy-binding oatmeal-farm-registry \
  --location=<REGION> \
  --project=oatmeal-farm-staging \
  --member="serviceAccount:<PROD-CLOUD-RUN-SA>@<PROD-PROJECT>.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
```

1. Update this section with the prod SA email and binding date.

---



## Team Handoff


| Teammate      | Task                       | What they need from this doc                                                    |
| ------------- | -------------------------- | ------------------------------------------------------------------------------- |
| **Aryan**     | Cloud Run staging services | `frontend-sa` for frontend; for backend DB use `stg-to-prod-db-ro-dev-project` + Cloud SQL connection name |
| **Sankeerth** | Saige Cloud Run + Saige secrets | Part A still open; backend `DB_*` done — see [STAGING_CLOUD_SQL_SETUP.md](./staging/STAGING_CLOUD_SQL_SETUP.md) |
| **Guia**      | CD workflow                | `STAGING_GCP_`* secret names + WIF workflow snippet above                       |
| **Vidyanand** | Cloud SQL                  | RO→prod path documented in [STAGING_CLOUD_SQL_SETUP.md](./staging/STAGING_CLOUD_SQL_SETUP.md) |


---



## Setup Commands Reference

Commands used to provision staging IAM. Safe to re-run; duplicate bindings are ignored.

### GitHub Actions service account

```bash
gcloud config set project oatmeal-farm-staging

gcloud iam service-accounts create github-actions-cicd \
  --display-name="GitHub Actions CI/CD" \
  --project=oatmeal-farm-staging

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



### Cloud Run service accounts

```bash
gcloud iam service-accounts create backend-sa --project=oatmeal-farm-staging
gcloud iam service-accounts create frontend-sa --project=oatmeal-farm-staging
gcloud iam service-accounts create saige-sa --project=oatmeal-farm-staging

for SA in backend-sa frontend-sa saige-sa; do
  gcloud projects add-iam-policy-binding oatmeal-farm-staging \
    --member="serviceAccount:${SA}@oatmeal-farm-staging.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"

  gcloud projects add-iam-policy-binding oatmeal-farm-staging \
    --member="serviceAccount:${SA}@oatmeal-farm-staging.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```



### Workload Identity Federation

```bash
gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

gcloud iam workload-identity-pools create "github-pool" \
  --project="oatmeal-farm-staging" \
  --location="global" \
  --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="oatmeal-farm-staging" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository=='Oatmeal-Farm-Network/oatmealfarmnetworkbackend'"

# Replace PROJECT_NUMBER with output from: gcloud projects describe oatmeal-farm-staging --format="value(projectNumber)"
gcloud iam service-accounts add-iam-policy-binding \
  "github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com" \
  --project="oatmeal-farm-staging" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/Oatmeal-Farm-Network/oatmealfarmnetworkbackend"
```



### Verify bindings

```bash
# List roles for a service account
gcloud projects get-iam-policy oatmeal-farm-staging \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:backend-sa@oatmeal-farm-staging.iam.gserviceaccount.com" \
  --format="table(bindings.role)"

# WIF impersonation binding on the deploy SA
gcloud iam service-accounts get-iam-policy \
  github-actions-cicd@oatmeal-farm-staging.iam.gserviceaccount.com \
  --project=oatmeal-farm-staging
```

---



## Related docs

- [CI/CD Task Assignments (Phase 1)](../backend_team_tasks/CI_CD_TASK_ASSIGNMENTS_P-1.md) — sprint scope and teammate tasks

