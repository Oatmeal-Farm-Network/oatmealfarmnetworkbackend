from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from routers import auth
from database import get_db, SessionLocal
import os
from dotenv import load_dotenv

load_dotenv()
print("SECRET_KEY loaded:", os.getenv("SECRET_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://oatmealfarmnewtorkbackend-802455386518.us-central1.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)

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