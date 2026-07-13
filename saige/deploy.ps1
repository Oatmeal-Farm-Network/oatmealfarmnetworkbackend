# Deploy Saige backend to Cloud Run.
# Run from this directory: .\deploy.ps1
# Requires: gcloud CLI authenticated.

$PROJECT   = "animated-flare-421518"
$REGION    = "us-central1"
$SERVICE   = "saige-backend"
$MAIN_SVC  = "oatmealfarmnewtorkbackend"
$IMAGE_TAG = "us-central1-docker.pkg.dev/$PROJECT/cloud-run-source-deploy/saige-backend:latest"

# SECRET_KEY must match the main backend's SECRET_KEY so JWTs can be verified.
$SECRET_KEY = $env:SECRET_KEY
if (-not $SECRET_KEY) {
    Write-Host "Fetching SECRET_KEY from main backend Cloud Run service..."
    $SECRET_KEY = gcloud run services describe $MAIN_SVC `
        --region=$REGION --project=$PROJECT `
        --format="value(spec.template.spec.containers[0].env.filter(name=SECRET_KEY).extract(value).flatten())" 2>$null
}
if (-not $SECRET_KEY) {
    Write-Error "SECRET_KEY not found. Set `$env:SECRET_KEY or ensure main backend has it configured."
    exit 1
}

$ENV_VARS = @(
    "SECRET_KEY=$SECRET_KEY",
    "GOOGLE_CLOUD_PROJECT=$PROJECT",
    "GOOGLE_CLOUD_LOCATION=$REGION",
    "FIRESTORE_DATABASE=charlie",
    "CHAT_HISTORY_DATABASE=chat-history",
    "FRONTEND_URL=https://www.oatmealfarmnetwork.com",
    "GEMINI_MODEL=gemini-2.5-flash-lite",
    "GOOGLE_GENAI_USE_VERTEXAI=true",
    "OFN_BACKEND_URL=https://oatmealfarmnewtorkbackend-802455386518.us-central1.run.app"
) -join ","

Write-Host "Building image via Cloud Build..."
gcloud builds submit --tag $IMAGE_TAG --project=$PROJECT
if (-not $?) { Write-Error "Build failed"; exit 1 }

Write-Host "Deploying to Cloud Run..."
gcloud run deploy $SERVICE `
    --image $IMAGE_TAG `
    --region $REGION `
    --project $PROJECT `
    --update-env-vars $ENV_VARS `
    --allow-unauthenticated

if (-not $?) { Write-Error "Deploy failed"; exit 1 }

Write-Host "Done. Testing health..."
Start-Sleep -Seconds 8
Invoke-RestMethod "https://$SERVICE-802455386518.$REGION.run.app/health"
