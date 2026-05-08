# Deploy Saige backend to Cloud Run.
# Run from this directory: .\deploy.ps1
# Requires: gcloud CLI authenticated, Docker running (or Cloud Build used instead).

$PROJECT   = "animated-flare-421518"
$REGION    = "us-central1"
$SERVICE   = "saige-backend"
$IMAGE_TAG = "us-central1-docker.pkg.dev/$PROJECT/cloud-run-source-deploy/saige-backend:latest"

# SECRET_KEY must match the main backend's SECRET_KEY so JWTs can be verified.
# Get this from: gcloud run services describe oatmealfarmnewtorkbackend --region=us-central1 --format="value(spec.template.spec.containers[0].env[SECRET_KEY])"
$SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"

Write-Host "Building image via Cloud Build..."
gcloud builds submit --tag $IMAGE_TAG --project=$PROJECT
if (-not $?) { Write-Error "Build failed"; exit 1 }

Write-Host "Deploying to Cloud Run (with env vars)..."
gcloud run deploy $SERVICE `
    --image $IMAGE_TAG `
    --region $REGION `
    --project $PROJECT `
    --update-env-vars "SECRET_KEY=$SECRET_KEY"

Write-Host "Done. Testing health..."
Start-Sleep -Seconds 5
Invoke-RestMethod "https://$SERVICE-802455386518.$REGION.run.app/health"
