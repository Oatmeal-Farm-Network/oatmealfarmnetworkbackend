"""
Over the Fence Social — FastAPI application (Saige-style isolated package).

Mounted routes live under /api/admin/mill (communities, channels, DMs, forums).
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import mill

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
