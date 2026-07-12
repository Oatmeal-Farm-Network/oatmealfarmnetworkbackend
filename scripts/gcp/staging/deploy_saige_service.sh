#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-oatmeal-farm-staging}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-oatmeal-farm-registry}"
SERVICE_NAME="${SERVICE_NAME:-oatmeal-saige-staging}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com}"
IMAGE_NAME="${IMAGE_NAME:-saige}"
COMMIT_SHA="${COMMIT_SHA:-$(git rev-parse --short=12 HEAD)}"
FRONTEND_URL="${FRONTEND_URL:-https://oatmeal-frontend-staging-lrviw4iujq-uc.a.run.app}"
ATTACH_RO_SQLSERVER_PATH="${ATTACH_RO_SQLSERVER_PATH:-false}"
CLOUDSQL_CONNECTION_NAME="${CLOUDSQL_CONNECTION_NAME:-animated-flare-421518:us-central1:oatmealailive}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${COMMIT_SHA}"

echo "Building image ${IMAGE_URI}"
gcloud builds submit ./saige --tag "${IMAGE_URI}" --project "${PROJECT_ID}"

secret_args="SECRET_KEY=SECRET_KEY:latest"
if gcloud secrets describe CRON_SECRET --project "${PROJECT_ID}" >/dev/null 2>&1; then
  secret_args="${secret_args},CRON_SECRET=CRON_SECRET:latest"
fi

extra_args=()
if [[ "${ATTACH_RO_SQLSERVER_PATH}" == "true" ]]; then
  extra_args+=(
    --set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}"
    --update-secrets "DB_HOST=DB_SERVER:latest,DB_USER=DB_USER:latest,DB_PASSWORD=DB_PASSWORD:latest,DB_NAME=DB_NAME:latest"
  )
fi

echo "Deploying ${SERVICE_NAME}"
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_URI}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --allow-unauthenticated \
  --port 8000 \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 10 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},FRONTEND_URL=${FRONTEND_URL},ALLOW_ALL_ORIGINS=false,GOOGLE_GENAI_USE_VERTEXAI=true,VERTEX_AI_MODEL=gemini-2.5-flash-lite,FIRESTORE_DATABASE=charlie,CHAT_HISTORY_DATABASE=chat-history,REDIS_ENABLED=false" \
  --set-secrets "${secret_args}" \
  "${extra_args[@]}"

echo "Deployed URL:"
gcloud run services describe "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.url)'
