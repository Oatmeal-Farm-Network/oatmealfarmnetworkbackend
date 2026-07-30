"""
Standalone Over the Fence (OTF) Social service entrypoint.

Livestock-style thin wrapper: mounts app.routers.mill on its own Cloud Run
service while mill remains dual-served from the main backend.

Run locally:
    uvicorn otf.api:app --reload --port 8004

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

from app.routers import mill  # noqa: E402

FRONTEND_URL = os.getenv("FRONTEND_URL", "")
OTF_FRONTEND_URL = os.getenv("OTF_FRONTEND_URL", "")
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
]
for origin in (FRONTEND_URL, OTF_FRONTEND_URL):
    if origin and origin not in ALLOWED_ORIGINS:
        ALLOWED_ORIGINS.append(origin)

app = FastAPI(title="Over the Fence Social API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mill.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "otf"}
