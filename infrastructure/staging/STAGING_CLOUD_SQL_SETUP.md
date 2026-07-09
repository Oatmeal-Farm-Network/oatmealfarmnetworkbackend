## APIs Enabled
- Cloud Run
- Cloud SQL Admin
- Artifact Registry
- IAM
- Secret Manager

## Access & Security
⚠️ VPC and service account lockdown pending — waiting for Bringesh to finalize IAM service accounts.
Once IAM is finalized, restrict database access to internal VPC only and remove public IP.

## Status
- [x] GCP project confirmed with billing enabled
- [x] Required APIs enabled
- [x] Cloud SQL instance provisioned
- [x] Database and user created
- [x] Credentials stored in Secret Manager
- [ ] VPC lockdown (pending Bringesh IAM finalization)