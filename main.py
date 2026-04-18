from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from routers import auth
from database import get_db, SessionLocal
import os
import models
from dotenv import load_dotenv

from routers import businesses
from routers import precision_ag
from routers import plant_knowledgebase
from routers import ingredient_knowledgebase
from routers import livestock
from routers import produce
from routers import processed_food
from routers import services
from routers import ranches
from routers import meat
from routers import forgot_password
from routers import weather
from routers import notes
from routers import crop_rotation
from routers import website_builder
from routers import website_ai
from routers import sfproducts
from routers import events
from routers import company_features
from routers import blog
from routers import accounting
from routers import animals

from routers.marketplace import marketplace_router
from marketplace_stripe import stripe_router

load_dotenv()

from fastapi import Request
from fastapi.responses import JSONResponse

ALLOWED_ORIGINS = [
    "http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:3000",
    "https://oatmealfarmnetwork-802455386518.us-central1.run.app",
    "https://oatmealfarmnewtorkbackend-802455386518.us-central1.run.app",
    "https://crop-detection-dcecevhvh5ard2ah.eastus-01.azurewebsites.net",
    "https://www.oatmealfarmnetwork.com", "https://oatmealfarmnetwork.com",
    "https://lkm-802455386518.us-central1.run.app",
    "https://lkm-mt7mh6zhoa-uc.a.run.app",
    "https://lkm-frontend-802455386518.us-central1.run.app",
    "https://lkm-frontend-mt7mh6zhoa-uc.a.run.app",
    "https://www.lkmcpa.com", "https://lkmcpa.com",
]

def _is_allowed_origin(origin: str) -> bool:
    """Return True if origin is in the static list or matches a registered custom domain in the DB."""
    if not origin:
        return False
    if origin in ALLOWED_ORIGINS:
        return True
    if origin.startswith("https://"):
        try:
            from sqlalchemy import text as sa_text
            clean = origin.replace("https://", "").replace("http://", "").rstrip("/")
            alt = clean[4:] if clean.startswith("www.") else f"www.{clean}"
            with SessionLocal() as db:
                row = db.execute(
                    sa_text("SELECT TOP 1 1 FROM BusinessWebsite WHERE CanonicalURL LIKE :pat OR CanonicalURL LIKE :alt"),
                    {"pat": f"%{clean}%", "alt": f"%{alt}%"}
                ).first()
                return row is not None
        except Exception:
            pass
    return False

class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """Replaces the static CORSMiddleware so registered custom domains are allowed automatically."""
    CORS_HEADERS = {
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept",
        "Access-Control-Max-Age": "86400",
    }

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")
        allowed = _is_allowed_origin(origin)

        if request.method == "OPTIONS":
            resp = Response(status_code=204)
            if allowed:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                for k, v in self.CORS_HEADERS.items():
                    resp.headers[k] = v
            return resp

        response = await call_next(request)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

app = FastAPI()

@app.on_event("startup")
async def _startup_migrations():
    """Idempotent one-time data fixups — run in a thread so they never block startup."""
    import asyncio
    from sqlalchemy import text as _t

    def _run():
        try:
            with SessionLocal() as _db:
                _db.execute(_t(
                    "UPDATE speciescategory SET SpeciesCategory = 'Herdsire' "
                    "WHERE SpeciesCategory = 'Stud' AND SpeciesID = 2"
                ))
                _db.commit()
        except Exception:
            pass

    asyncio.get_event_loop().run_in_executor(None, _run)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin", "")
    headers = {}
    if _is_allowed_origin(origin):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers=headers,
    )

app.add_middleware(DynamicCORSMiddleware)

app.include_router(auth.router)
app.include_router(businesses.router)
app.include_router(precision_ag.router)
app.include_router(plant_knowledgebase.router)
app.include_router(ingredient_knowledgebase.router)
app.include_router(livestock.router)
app.include_router(produce.router)
app.include_router(processed_food.router)
app.include_router(services.router)
app.include_router(ranches.router)
app.include_router(meat.router)

app.include_router(marketplace_router, prefix="/api/marketplace")
app.include_router(stripe_router, prefix="/api/marketplace/payments")
app.include_router(forgot_password.router)
app.include_router(weather.router)
app.include_router(notes.router)
app.include_router(crop_rotation.router)
app.include_router(website_builder.router)
app.include_router(website_ai.router)
app.include_router(sfproducts.router)
app.include_router(events.router)
app.include_router(company_features.router)
app.include_router(blog.router)
app.include_router(accounting.router)
app.include_router(animals.router)


# ── Public testimonials endpoint (used by website blocks) ─────────
@app.get("/api/testimonials")
def get_public_testimonials(BusinessID: int, db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT TestimonialsID, CustomerName AS AuthorName,
               Testimonial AS Content, Rating,
               City, State, Organization, URL AS Website,
               TestimonialDate, PeopleID, Name,
               AnimalID, AnimalName, TestimonialsType
        FROM Testimonials
        WHERE CustID = :bid
        ORDER BY testimonialsOrder, TestimonialsID DESC
    """), {"bid": BusinessID}).fetchall()
    return [dict(r._mapping) for r in rows]


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/test-env")
def test_env():
    return {
        "server": os.getenv("DB_SERVER"),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password_set": bool(os.getenv("DB_PASSWORD"))
    }


@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    from sqlalchemy import text
    result = db.execute(text("SELECT 1")).fetchone()
    return {"db": "connected", "result": str(result)}


@app.get("/test-people2")
def test_people2():
    from sqlalchemy import text
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT TOP 1 PeopleID FROM People")).fetchone()
        return {"result": str(result)}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()