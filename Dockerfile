FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    freetds-dev \
    freetds-bin \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY . .

# Max-accuracy photo biomass: DINOv2 + multi-domain calibration (CPU torch)
ENV BIOMASS_SAMPLE_AREA_M2=0.25 \
    BIOMASS_IMG_SIZE=392 \
    BIOMASS_USE_DINO=true \
    BIOMASS_REQUIRE_DINO=false \
    BIOMASS_CALIBRATION_PATH=/app/biomass_estimator/calibration_multidomain.npz \
    BIOMASS_GCS_BUCKET=oatmeal-farm-network-images \
    BIOMASS_GCS_PREFIX=biomass-uploads \
    TORCH_HOME=/app/.cache/torch

# Prefetch DINOv2 weights into the image (avoids first-request download)
RUN mkdir -p /app/.cache/torch/hub \
    && python -c "import torch; torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14', pretrained=True); print('DINOv2 weights cached')"

# Cloud Run: require --memory 8Gi --cpu 2 --timeout 300 for DINO inference
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
