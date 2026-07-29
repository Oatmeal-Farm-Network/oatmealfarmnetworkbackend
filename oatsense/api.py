"""
Standalone Oatsense service entrypoint.

Owns precision-ag / crop-detection APIs and proxies CropMonitor as a
single BFF for the Oatsense website.

Run locally:
    uvicorn oatsense.api:app --reload --port 8003

On Cloud Run the Dockerfile CMD does the same without --reload.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the repo root is on sys.path so `from app.routers …` resolves.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv()

from app.routers import (  # noqa: E402
    crop_monitor_proxy,
    field_activity,
    field_assessment_report,
    field_health,
    field_health_alerts,
    field_maturity,
    precision_ag,
    precision_ag_features,
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "")
OATSENSE_FRONTEND_URL = os.getenv("OATSENSE_FRONTEND_URL", "")
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
]
for origin in (FRONTEND_URL, OATSENSE_FRONTEND_URL):
    if origin and origin not in ALLOWED_ORIGINS:
        ALLOWED_ORIGINS.append(origin)

app = FastAPI(title="Oatsense API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(precision_ag.router)
app.include_router(precision_ag_features.router)
app.include_router(field_maturity.router)
app.include_router(field_assessment_report.router)
app.include_router(field_activity.router)
app.include_router(field_health.router)
app.include_router(field_health_alerts.router)
app.include_router(crop_monitor_proxy.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "oatsense"}
