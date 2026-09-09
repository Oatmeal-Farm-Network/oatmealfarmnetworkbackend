#!/usr/bin/env bash
# Max-accuracy photo biomass on Cloud Run (DINOv2 + torch CPU).
# Usage:
#   SERVICE=oatmealfarmnewtorkbackend REGION=us-central1 PROJECT=animated-flare-421518 \
#     bash scripts/set_biomass_cloudrun_env.sh
set -euo pipefail

PROJECT="${PROJECT:-animated-flare-421518}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-oatmealfarmnewtorkbackend}"

gcloud run services update "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --memory=4Gi \
  --cpu=2 \
  --timeout=300 \
  --cpu-boost \
  --update-env-vars="BIOMASS_SAMPLE_AREA_M2=0.25,BIOMASS_IMG_SIZE=518,BIOMASS_USE_DINO=true,BIOMASS_REQUIRE_DINO=false,BIOMASS_CALIBRATION_PATH=/app/biomass_estimator/calibration_multidomain.npz,BIOMASS_GCS_BUCKET=oatmeal-farm-network-images,BIOMASS_GCS_PREFIX=biomass-uploads,TORCH_HOME=/app/.cache/torch"

echo "Updated Cloud Run ${SERVICE} for max-accuracy DINOv2 biomass (4Gi / 2 CPU / 300s)."
