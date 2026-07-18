# Staging Writable Database (Cloned from Prod)

**Owner:** Bringesh
**Staging project:** `oatmeal-farm-staging`
**Region:** `us-central1`
**Last updated:** July 2026

> This supersedes the read-only-to-prod design in
> [STAGING_CLOUD_SQL_SETUP.md](./STAGING_CLOUD_SQL_SETUP.md).

## Why

Staging previously connected **read-only** to the prod Cloud SQL instance,
which blocked write testing (e.g. creating user accounts). Staging now has its
own **writable** Cloud SQL SQL Server instance, cloned from prod.

Prod data is pre-launch, so a full clone is acceptable. **Revisit once real
user data exists** — at that point switch to schema-only + synthetic/sanitized
data to avoid copying PII into a write-enabled environment.

## Architecture

```text
Cloud Run (oatmeal-backend-staging)
  runtime SA: stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam
  env: INSTANCE_CONNECTION_NAME=oatmeal-farm-staging:us-central1:oatmeal-staging-sqlserver
       SKIP_SCHEMA_ENSURE=false
       |  Cloud SQL Python Connector + pytds
       v
  Staging SQL Server: oatmeal-staging-sqlserver (SQLSERVER_2022_EXPRESS)
  DB: Oatmealailivedb (641 tables)
  App login: oatmeal_app (db_datareader / db_datawriter / db_ddladmin)
```

## Resources (Terraform: `infra/staging-sqlserver/`)

| Resource | Value |
|----------|-------|
| Instance | `oatmeal-staging-sqlserver` (2022 Express, `db-custom-1-3840`, zonal/no-HA) |
| Database | `Oatmealailivedb` (created by the BAK import, not by Terraform) |
| App login | `oatmeal_app` |
| Transfer bucket | `oatmeal-farm-staging-sql-transfer` (7-day object lifecycle) |
| TF state bucket | `oatmeal-staging-tfstate` |
| Secrets | `staging-sqlserver-root-password`, `staging-sqlserver-app-password`; app reads `DB_USER` / `DB_PASSWORD` / `DB_NAME` |

Passwords are stored in Secret Manager and mirrored into `terraform.tfvars`
(gitignored) so Terraform does not revert them on the next apply.

## Setup steps performed

1. `terraform apply` — instance, app login, transfer bucket, cross-project IAM.
2. `clone_prod_to_staging.ps1` — `export bak` (prod) -> `import bak` (staging). 641 tables.
3. `post_restore.sql` — re-link `oatmeal_app`, grant datareader/datawriter/ddladmin.
4. Rotated root + app passwords (via `terraform apply`; values in Secret Manager).
5. Repointed Cloud Run: `INSTANCE_CONNECTION_NAME`, `SKIP_SCHEMA_ENSURE=false`,
   `DB_USER=oatmeal_app`, `DB_PASSWORD` -> app password; updated CD workflow.
6. Removed runtime SA `roles/cloudsql.client` on the prod project.

## Refreshing staging from prod

```powershell
cd infra/staging-sqlserver
./clone_prod_to_staging.ps1 -Refresh   # drops + re-imports the DB (WIPES staging data)
# then re-apply post_restore.sql — a fresh restore re-orphans oatmeal_app
```

## Connecting manually

```powershell
cloud-sql-proxy --port 1433 oatmeal-farm-staging:us-central1:oatmeal-staging-sqlserver
# sqlcmd -S 127.0.0.1,1433 -U oatmeal_app -d Oatmealailivedb -C
# password: gcloud secrets versions access latest --secret=staging-sqlserver-app-password --project=oatmeal-farm-staging
```

## Outstanding

- Merge the CD workflow change into `GCP/backend-staging` so future deploys use
  the new instance (the live service is already repointed).
- Drop the now-inert `stg_to_prod_ro` login on prod (needs prod sysadmin):
  `DROP USER IF EXISTS [stg_to_prod_ro]` (in `Oatmealailivedb`) and
  `DROP LOGIN [stg_to_prod_ro]` (in `master`).
- Pre-existing app bug (unrelated to this migration): a background job
  references a missing table `FarmInput` (`Invalid object name 'FarmInput'`).
- Post-launch: switch from full clone to schema-only + synthetic/sanitized data.
