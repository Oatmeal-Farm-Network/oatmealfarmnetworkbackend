variable "staging_project_id" {
  type    = string
  default = "oatmeal-farm-staging"
}

variable "prod_project_id" {
  type    = string
  default = "animated-flare-421518"
}

variable "prod_instance_name" {
  type    = string
  default = "oatmealailive"
}

variable "region" {
  type    = string
  default = "us-central1"
}

# Must be >= prod's major version. Prod is SQLSERVER_2022_STANDARD, so this must
# be a 2022 build. EXPRESS has no license cost and a 10 GB/DB cap; prod DB is
# ~2.92 GB, so it fits. If `gcloud sql import bak` reports an edition-feature
# error (e.g. TDE), switch this to SQLSERVER_2022_WEB and re-apply.
variable "database_version" {
  type    = string
  default = "SQLSERVER_2022_EXPRESS"
}

# SQL Server minimum machine shape (1 vCPU / 3.75 GB) — cheapest option.
variable "tier" {
  type    = string
  default = "db-custom-1-3840"
}

variable "sa_admin_root_password" {
  type      = string
  sensitive = true
}

variable "app_db_login" {
  type    = string
  default = "oatmeal_app"
}

variable "app_db_password" {
  type      = string
  sensitive = true
}

# Cloud Run runtime SA that will connect to the new staging DB.
variable "runtime_sa_email" {
  type    = string
  default = "stg-to-prod-db-ro-dev-project@oatmeal-farm-staging.iam.gserviceaccount.com"
}
