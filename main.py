from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
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

from routers.marketplace import marketplace_router
from marketplace_stripe import stripe_router

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://oatmealfarmnetwork-802455386518.us-central1.run.app",
        "https://oatmealfarmnewtorkbackend-802455386518.us-central1.run.app",
        "https://crop-detection-dcecevhvh5ard2ah.eastus-01.azurewebsites.net",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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