# app.database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv
import pymssql


load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_SERVER = os.getenv("DB_SERVER")
# When set (Cloud Run staging/prod), use Cloud SQL Python Connector instead of
# DB_SERVER=127.0.0.1 Auth Proxy TCP — SQL Server on Cloud Run often has no
# listener on localhost:1433 even with --set-cloudsql-instances.
INSTANCE_CONNECTION_NAME = (os.getenv("INSTANCE_CONNECTION_NAME") or "").strip()

_connector = None


def _get_connector():
    global _connector
    if _connector is None:
        from google.cloud.sql.connector import Connector, IPTypes

        ip_type = IPTypes.PRIVATE if os.getenv("PRIVATE_IP") else IPTypes.PUBLIC
        _connector = Connector(ip_type=ip_type, refresh_strategy="LAZY")
    return _connector


def _connect_raw():
    """Open a raw DB-API connection (pymssql locally, pytds via Connector on Cloud Run)."""
    if INSTANCE_CONNECTION_NAME:
        return _get_connector().connect(
            INSTANCE_CONNECTION_NAME,
            "pytds",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
        )
    return pymssql.connect(
        server=DB_SERVER,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        timeout=30,
        login_timeout=15,
    )


def _build_engine():
    if INSTANCE_CONNECTION_NAME:
        connector = _get_connector()

        def getconn():
            return connector.connect(
                INSTANCE_CONNECTION_NAME,
                "pytds",
                user=DB_USER,
                password=DB_PASSWORD,
                db=DB_NAME,
            )

        return create_engine(
            "mssql+pytds://",
            creator=getconn,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=10,
        )

    url = (
        f"mssql+pymssql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_SERVER}/{DB_NAME}"
    )
    return create_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=10,
        connect_args={"timeout": 30, "login_timeout": 15},
    )


# Kept for callers that still build URLs; prefer engine / SessionLocal.
SQLALCHEMY_DATABASE_URL = (
    f"mssql+pymssql://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}/{DB_NAME}"
    if not INSTANCE_CONNECTION_NAME
    else "mssql+pytds://"
)

engine = _build_engine()

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
    conn = _connect_raw()
    return conn.cursor(as_dict=True)


def get_raw_conn():
    conn = _connect_raw()
    try:
        yield conn
    finally:
        conn.close()
