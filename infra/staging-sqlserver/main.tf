# Prod instance's service agent — needed so its export can WRITE the .bak.
data "google_sql_database_instance" "prod" {
  project = var.prod_project_id
  name    = var.prod_instance_name
}

resource "google_sql_database_instance" "staging" {
  name                = "oatmeal-staging-sqlserver"
  project             = var.staging_project_id
  region              = var.region
  database_version    = var.database_version
  root_password       = var.sa_admin_root_password
  deletion_protection = false # staging

  settings {
    tier              = var.tier
    availability_type = "ZONAL" # no HA — cheaper
    disk_size         = 10
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    backup_configuration {
      enabled = true
    }

    ip_configuration {
      ipv4_enabled = true # Cloud SQL Python Connector uses the public path
    }

    deletion_protection_enabled = false
  }
}

# Server-level SQL login for the app (writable). DB-level user mapping +
# role grants happen AFTER the restore, in the clone script (T-SQL), because
# the BAK import creates the database itself.
resource "google_sql_user" "app" {
  name     = var.app_db_login
  instance = google_sql_database_instance.staging.name
  project  = var.staging_project_id
  password = var.app_db_password
}

# Bucket used to hand the .bak from prod -> staging.
resource "google_storage_bucket" "transfer" {
  name                        = "${var.staging_project_id}-sql-transfer"
  project                     = var.staging_project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = 7 # auto-delete old baks
    }
    action {
      type = "Delete"
    }
  }
}

# Prod instance SA must be able to WRITE the export into the bucket.
resource "google_storage_bucket_iam_member" "prod_export" {
  bucket = google_storage_bucket.transfer.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${data.google_sql_database_instance.prod.service_account_email_address}"
}

# Staging instance SA must be able to READ the .bak for import.
resource "google_storage_bucket_iam_member" "staging_import" {
  bucket = google_storage_bucket.transfer.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_sql_database_instance.staging.service_account_email_address}"
}

# Let the Cloud Run runtime SA connect to the new (in-project) instance.
resource "google_project_iam_member" "runtime_cloudsql_client" {
  project = var.staging_project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${var.runtime_sa_email}"
}

output "instance_connection_name" {
  value = google_sql_database_instance.staging.connection_name
}

output "transfer_bucket" {
  value = google_storage_bucket.transfer.name
}
