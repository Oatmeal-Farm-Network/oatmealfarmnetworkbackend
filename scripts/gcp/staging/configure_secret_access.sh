#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-oatmeal-farm-staging}"
SAIGE_SA="${SAIGE_SA:-saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com}"
ATTACH_RO_SQLSERVER_PATH="${ATTACH_RO_SQLSERVER_PATH:-false}"

grant_secret_access() {
  local secret_name="$1"
  echo "Granting ${SAIGE_SA} access to ${secret_name}"
  gcloud secrets add-iam-policy-binding "${secret_name}" \
    --project "${PROJECT_ID}" \
    --member "serviceAccount:${SAIGE_SA}" \
    --role "roles/secretmanager.secretAccessor"
}

grant_secret_access SECRET_KEY

if gcloud secrets describe CRON_SECRET --project "${PROJECT_ID}" >/dev/null 2>&1; then
  grant_secret_access CRON_SECRET
fi

for optional_secret in GOOGLE_API_KEY GEMINI_API_KEY WEATHER_API_KEY REDIS_URL; do
  if gcloud secrets describe "${optional_secret}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    grant_secret_access "${optional_secret}"
  fi
done

if [[ "${ATTACH_RO_SQLSERVER_PATH}" == "true" ]]; then
  for db_secret in DB_SERVER DB_USER DB_PASSWORD DB_NAME; do
    grant_secret_access "${db_secret}"
  done
fi

echo "Saige secret IAM bindings updated for staging."
