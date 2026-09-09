# Cloud Run notes for max-accuracy photo biomass (DINOv2)
#
# Image already sets:
#   BIOMASS_USE_DINO=true
#   BIOMASS_REQUIRE_DINO=true
#   BIOMASS_CALIBRATION_PATH=/app/biomass_estimator/calibration_multidomain.npz
#
# After deploying a new image built from Dockerfile, also run:
#   bash scripts/set_biomass_cloudrun_env.sh
#
# Recommended Cloud Run resources (also set by that script):
#   memory: 4Gi
#   cpu: 2
#   timeout: 300s
#
# One-time GCS setup (from a machine with ADC):
#   python scripts/ensure_biomass_cloud.py
#
# DB table FieldBiomassAnalysis is created on API startup and by
# scripts/ensure_biomass_cloud.py / biomass_estimator/table.py on first upload.
