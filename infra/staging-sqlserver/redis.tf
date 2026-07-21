# Empty Redis (Memorystore) for staging. Data is intentionally NOT cloned from
# prod — Redis is a cache that repopulates from the database. BASIC tier (no HA)
# keeps cost low, matching the prod instance's tier/version/size.
resource "google_redis_instance" "staging" {
  project        = var.staging_project_id
  name           = var.redis_name
  tier           = "BASIC"
  memory_size_gb = var.redis_memory_gb
  region         = var.region
  redis_version  = var.redis_version
  display_name   = "Farm advisory Redis (staging)"
}

output "redis_host" {
  value = google_redis_instance.staging.host
}

output "redis_port" {
  value = google_redis_instance.staging.port
}
