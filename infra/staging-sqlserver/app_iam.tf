# Phase 3 — wire the backend Cloud Run runtime SA to the staging datastores.

# Firestore read/write in the staging project (news, Lavendir, Thaiyme, Tarrigon).
resource "google_project_iam_member" "runtime_datastore_user" {
  project = var.staging_project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${var.runtime_sa_email}"
}

# Read/write the staging image bucket (uploads: animals, blog, website, logos,
# equipment, ingredients). Bucket was created manually, so this manages only the
# IAM binding, not the bucket itself.
resource "google_storage_bucket_iam_member" "runtime_images_staging" {
  bucket = var.images_bucket_staging
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.runtime_sa_email}"
}
