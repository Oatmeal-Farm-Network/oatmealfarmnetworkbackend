## APIs Enabled
The following GCP APIs have been enabled on the `oatmeal-farm-staging` project:

| API | Purpose |
|-----|---------|
| Cloud Run | Run containerized backend services |
| Cloud SQL Admin | Manage and connect to PostgreSQL database |
| Artifact Registry | Store and manage Docker images |
| IAM | Control access and permissions |
| Secret Manager | Securely store credentials and connection strings |

## Access & Security
> ⚠️ **Action Pending — Bringesh (IAM Setup)**
> Database access lockdown cannot be completed until Bringesh finalizes the IAM service accounts.

Once IAM service accounts are finalized, the following will be done:
- Restrict database access to **internal VPC only** (no public internet access)
- Remove the current public IP (`35.255.174.192`)
- Bind database access to the backend's dedicated service account only

Until then, the database is reachable via its public IP but protected by Cloud SQL user credentials stored in Secret Manager.

## Setup Status

| Task | Status |
|------|--------|
| GCP project confirmed with billing enabled | ✅ Done |
| Required GCP APIs enabled | ✅ Done |
| Cloud SQL instance provisioned (PostgreSQL 15) | ✅ Done |
| Database and user created | ✅ Done |
| Credentials stored in Secret Manager | ✅ Done |
| VPC lockdown & service account binding | ⏳ Pending Bringesh's IAM finalization |