# Staging-only Saige Cloud Run deploy helper.
# Run from repo root or from the saige directory:
#   pwsh ./saige/deploy.ps1
#
# Prereqs:
# - gcloud CLI installed and authenticated
# - Access to the oatmeal-farm-staging project
# - Artifact Registry repository already created
# - Cloud Build API enabled
# - Required Secret Manager secrets already provisioned (`SECRET_KEY`; `CRON_SECRET` optional but recommended)

param(
    [string]$ProjectId = "oatmeal-farm-staging",
    [string]$Region = "us-central1",
    [string]$Repository = "oatmeal-farm-registry",
    [string]$ServiceName = "oatmeal-saige-staging",
    [string]$ServiceAccount = "saige-sa@oatmeal-farm-staging.iam.gserviceaccount.com",
    [string]$ImageName = "saige",
    [string]$CommitSha = "",
    [string]$FrontendUrl = "https://staging.oatmealfarmnetwork.com"
)

$ErrorActionPreference = "Stop"

if (-not $CommitSha) {
    $CommitSha = (git rev-parse --short=12 HEAD).Trim()
}

$ImageUri = "$Region-docker.pkg.dev/$ProjectId/$Repository/$ImageName`:$CommitSha"

Write-Host "Building Saige image: $ImageUri"
gcloud builds submit ./saige --tag $ImageUri --project $ProjectId

Write-Host "Deploying $ServiceName to Cloud Run (staging)"
gcloud run deploy $ServiceName `
    --image $ImageUri `
    --project $ProjectId `
    --region $Region `
    --service-account $ServiceAccount `
    --allow-unauthenticated `
    --port 8000 `
    --memory 2Gi `
    --cpu 2 `
    --min-instances 1 `
    --max-instances 10 `
    --set-env-vars "GOOGLE_CLOUD_PROJECT=$ProjectId,GOOGLE_CLOUD_LOCATION=$Region,FRONTEND_URL=$FrontendUrl,ALLOW_ALL_ORIGINS=false,GOOGLE_GENAI_USE_VERTEXAI=true,VERTEX_AI_MODEL=gemini-2.5-flash-lite,FIRESTORE_DATABASE=charlie,CHAT_HISTORY_DATABASE=chat-history,REDIS_ENABLED=false" `
    --set-secrets "SECRET_KEY=SECRET_KEY:latest,CRON_SECRET=CRON_SECRET:latest"

$Url = gcloud run services describe $ServiceName `
    --project $ProjectId `
    --region $Region `
    --format "value(status.url)"

Write-Host "Saige staging URL: $Url"
