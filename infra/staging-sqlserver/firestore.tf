# Project numbers, used to build the Firestore service-agent emails for IAM.
data "google_project" "staging" {
  project_id = var.staging_project_id
}

data "google_project" "prod" {
  project_id = var.prod_project_id
}

# Firestore databases in staging, cloned from prod (artemis, charlie,
# chat-history). Terraform creates the EMPTY databases; data is loaded
# separately via `gcloud firestore export` (prod) -> bucket -> `import` (staging).
# Note: export/import does NOT carry security rules or composite indexes —
# handle those separately (google_firestore_index / rules deploy).
resource "google_firestore_database" "staging" {
  for_each = toset(var.firestore_databases)

  project         = var.staging_project_id
  name            = each.value
  location_id     = var.region
  type            = "FIRESTORE_NATIVE"
  deletion_policy = "DELETE" # staging
}

# Firestore export/import moves data through the existing transfer bucket
# (same region as the databases — required by Firestore export). The prod
# Firestore service agent writes exports; the staging one reads them for import.
# Firestore export/import needs bucket-level access (storage.buckets.get) in
# addition to object access, so grant storage.admin scoped to THIS bucket only
# (roles/storage.objectAdmin/objectViewer alone lack buckets.get and fail).
resource "google_storage_bucket_iam_member" "firestore_prod_export" {
  bucket = google_storage_bucket.transfer.name
  role   = "roles/storage.admin"
  member = "serviceAccount:service-${data.google_project.prod.number}@gcp-sa-firestore.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "firestore_staging_import" {
  bucket     = google_storage_bucket.transfer.name
  role       = "roles/storage.admin"
  member     = "serviceAccount:service-${data.google_project.staging.number}@gcp-sa-firestore.iam.gserviceaccount.com"
  depends_on = [google_firestore_database.staging]
}

output "firestore_databases" {
  value = [for db in google_firestore_database.staging : db.name]
}
