"""
Standalone Livestock of America (LOA) API entrypoint.

Serves breed KB, livestock marketplace, ranches, animals, herd health, and auth
for the LOA frontend Cloud Run site.

Run locally:
    uvicorn livestock.api:app --reload --port 8000

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

from app.routers import animals, auth, herd_health, livestock, ranches  # noqa: E402
from app.routers.marketplace import marketplace_router  # noqa: E402


def _cors_origins(*env_values: str) -> list[str]:
    """Build allow_origins from local defaults + comma-separated FRONTEND_URL env values."""
    origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ]
    for raw in env_values:
        if not raw:
            continue
        for part in raw.split(","):
            origin = part.strip().rstrip("/")
            if origin and origin not in origins:
                origins.append(origin)
    return origins


FRONTEND_URL = os.getenv("FRONTEND_URL", "")
LOA_FRONTEND_URL = os.getenv("LOA_FRONTEND_URL", "")
ALLOWED_ORIGINS = _cors_origins(FRONTEND_URL, LOA_FRONTEND_URL)

app = FastAPI(title="Livestock of America API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Breed / species knowledge base
app.include_router(livestock.router)
# Livestock marketplace (for-sale, studs, animal detail, filters)
app.include_router(marketplace_router, prefix="/api/marketplace")
# Ranch directory
app.include_router(ranches.router)
# Animal CRUD (seller / herd manager)
app.include_router(animals.router)
# Herd health
app.include_router(herd_health.router)
# Auth (same JWT SECRET_KEY as main backend when secrets match)
app.include_router(auth.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "livestock"}
