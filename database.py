# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv
import pymssql


load_dotenv()

SQLALCHEMY_DATABASE_URL = (
    f"mssql+pymssql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_SERVER')}/{os.getenv('DB_NAME')}"
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=60,      # recycle connections every 60s — prevents stale connections on Cloud Run
    pool_size=5,
    max_overflow=10,
    connect_args={"timeout": 30, "login_timeout": 15},  # 30s query / 15s login — handles cold starts
)

# Declarative base
Base = declarative_base()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_cursor():
    conn = pymssql.connect(
        server=os.getenv("DB_SERVER"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        timeout=10,
        login_timeout=10,
    )
    return conn.cursor(as_dict=True)