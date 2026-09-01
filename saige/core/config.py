# --- core/config.py --- (Centralized configuration)
import os
import sys
from typing import Optional
from urllib.parse import quote
from dotenv import load_dotenv

from core.paths import DEFAULT_MEDIA_DIR, SAIGE_ROOT

# Prefer saige/.env regardless of process cwd; keep default load for local overrides.
load_dotenv(SAIGE_ROOT / ".env")
load_dotenv()

# ============================================================================
# FEATURE AVAILABILITY FLAGS
# ============================================================================

# Firestore client (needed by chat history; also used by RAG)
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    print("[Warning] google-cloud-firestore not installed. Chat history will be disabled.")
    FIRESTORE_AVAILABLE = False

# Chat-time vector RAG needs Firestore + vector types + embeddings.
# pymssql is only required for SQL→Firestore sync jobs — do not gate RAG on it.
RAG_AVAILABLE = False
SQL_SYNC_AVAILABLE = False
if FIRESTORE_AVAILABLE:
    try:
        from google.cloud.firestore_v1.vector import Vector  # noqa: F401
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure  # noqa: F401
        from langchain_google_genai import GoogleGenerativeAIEmbeddings  # noqa: F401
        RAG_AVAILABLE = True
    except ImportError:
        print("[Warning] RAG dependencies not installed (vector/embeddings). Vector RAG disabled.")
    try:
        import pymssql  # noqa: F401
        SQL_SYNC_AVAILABLE = True
    except ImportError:
        print("[Warning] pymssql not installed. SQL→Firestore sync disabled (chat RAG still ok).")
else:
    print("[Warning] RAG disabled (requires Firestore).")

try:
    import requests
    WEATHER_AVAILABLE = True
except ImportError:
    print("[Warning] requests not installed. Weather service will be disabled.")
    WEATHER_AVAILABLE = False
    requests = None

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    print("[Warning] redis not installed. Redis features will be disabled.")
    REDIS_AVAILABLE = False
    redis = None

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Cloud Run SQL Server: use the Python Connector (see data/sql/connect.py).
# DB_SERVER is the Secret Manager name OFN backend already mounts.
INSTANCE_CONNECTION_NAME = (os.getenv("INSTANCE_CONNECTION_NAME") or "").strip()

DB_CONFIG = {
    "host": (os.getenv("DB_HOST") or os.getenv("DB_SERVER") or "").strip(),
    "port": int(os.getenv("DB_PORT", "1433").strip()) if os.getenv("DB_PORT") else 1433,
    "user": os.getenv("DB_USER", "").strip(),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "").strip(),
}

ALLOWED_TABLES = [
    "Speciesavailable", "Speciesbreedlookuptable", "Speciescategory",
    "Speciescolorlookuptable", "Speciespatternlookuptable", "Speciesregistrationtypelookuptable",
]

# ============================================================================
# GCP CONFIGURATION
# ============================================================================

GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1").strip()
GCP_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

# ============================================================================
# RAG CONFIGURATION
# ============================================================================

EMBEDDING_MODEL = "text-embedding-004"
TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", "10"))
RAG_DENSE_CANDIDATES = int(os.getenv("RAG_DENSE_CANDIDATES", "20"))
RAG_LEXICAL_CANDIDATES = int(os.getenv("RAG_LEXICAL_CANDIDATES", "20"))
RAG_RERANK_TOP_N = int(os.getenv("RAG_RERANK_TOP_N", "10"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.15"))
RAG_CACHE_TTL_SECONDS = int(os.getenv("RAG_CACHE_TTL_SECONDS", "900"))
RAG_CACHE_ENABLED = os.getenv("RAG_CACHE_ENABLED", "true").lower() == "true"
RAG_HYBRID_ENABLED = os.getenv("RAG_HYBRID_ENABLED", "true").lower() == "true"
RAG_RERANK_ENABLED = os.getenv("RAG_RERANK_ENABLED", "true").lower() == "true"
RAG_REWRITE_ENABLED = os.getenv("RAG_REWRITE_ENABLED", "true").lower() == "true"
RAG_LEXICAL_SCAN_LIMIT = int(os.getenv("RAG_LEXICAL_SCAN_LIMIT", "200"))
CHUNK_TARGET_CHARS = int(os.getenv("CHUNK_TARGET_CHARS", "2800"))  # ~700 tokens
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "280"))
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE", "charlie").strip()
CHAT_HISTORY_DATABASE = os.getenv("CHAT_HISTORY_DATABASE", "chat-history").strip()
LIVESTOCK_KNOWLEDGE_COLLECTION = "livestock_knowledge"
PLANT_KNOWLEDGE_COLLECTION = "plant_knowledge"
BAKASURA_DOCS_COLLECTION = "bakasura-docs"
NEWS_ARTICLES_COLLECTION = "news_articles"
HITL_CHARLIE_COLLECTION = "hitl-charlie"
SAIGE_LEARNINGS_COLLECTION = "saige_learnings"
# Backward-compatible alias
FIRESTORE_COLLECTION = LIVESTOCK_KNOWLEDGE_COLLECTION

SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
OFN_BACKEND_URL = os.getenv("OFN_BACKEND_URL", "http://localhost:8000").rstrip("/")
SPECIALIST_TIMEOUT_SECONDS = float(os.getenv("SPECIALIST_TIMEOUT_SECONDS", "40"))
# When Redis is enabled, refuse MemorySaver fallback unless explicitly allowed
REDIS_ALLOW_MEMORY_FALLBACK = os.getenv("REDIS_ALLOW_MEMORY_FALLBACK", "false").lower() == "true"

# ============================================================================
# ASSESSMENT CONFIGURATION
# ============================================================================

MAX_QUESTIONS = 2

# ============================================================================
# API CONFIGURATION
# ============================================================================

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
ALLOW_ALL_ORIGINS = os.getenv("ALLOW_ALL_ORIGINS", "false").lower() == "true"

# ============================================================================
# CHAT HISTORY CONFIGURATION
# ============================================================================

# OFN (default / legacy) and LOA use separate top-level Firestore collections
# so chat history never mixes across products. Auth (JWT) is shared.
THREADS_COLLECTION = os.getenv("THREADS_COLLECTION", "threads").strip() or "threads"
THREADS_COLLECTION_LOA = os.getenv("THREADS_COLLECTION_LOA", "loa_threads").strip() or "loa_threads"

_VALID_PRODUCTS = frozenset({"ofn", "loa"})


def normalize_chat_product(product: Optional[str]) -> str:
    """Map request product/source to ofn|loa. Default ofn for backward compatibility."""
    raw = (product or "ofn").strip().lower()
    if raw in ("loa", "livestock", "livestock_of_america", "livestock-of-america"):
        return "loa"
    if raw in ("ofn", "oatmeal", "oatmeal_farm_network", "oatmeal-farm-network"):
        return "ofn"
    return "ofn" if raw not in _VALID_PRODUCTS else raw


def threads_collection_for(product: Optional[str]) -> str:
    """Firestore collection name for Saige chat threads by product."""
    return THREADS_COLLECTION_LOA if normalize_chat_product(product) == "loa" else THREADS_COLLECTION

# ============================================================================
# REDIS CONFIGURATION (Environment-agnostic: works for local and GCP Memorystore)
# ============================================================================

REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "").strip() or None
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "") or None  # None if empty
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"
_redis_ssl_cert_reqs_raw = os.getenv("REDIS_SSL_CERT_REQS", "required").strip().lower()
_valid_redis_ssl_cert_reqs = {"required", "optional", "none"}
if _redis_ssl_cert_reqs_raw not in _valid_redis_ssl_cert_reqs:
    print(f"[Config] [WARN] Invalid REDIS_SSL_CERT_REQS='{_redis_ssl_cert_reqs_raw}', defaulting to 'required'")
    REDIS_SSL_CERT_REQS = "required"
else:
    REDIS_SSL_CERT_REQS = _redis_ssl_cert_reqs_raw

# Message buffer settings (Task 3 names)
SHORT_TERM_N = int(os.getenv("SHORT_TERM_N", os.getenv("MESSAGE_BUFFER_SIZE", "20")))  # Last N messages
SHORT_TERM_TTL_SECONDS = int(
    os.getenv("SHORT_TERM_TTL_SECONDS", os.getenv("MESSAGE_BUFFER_TTL_SECONDS", "86400"))
)  # 24h default

# Backward-compatible aliases
MESSAGE_BUFFER_SIZE = SHORT_TERM_N
MESSAGE_BUFFER_TTL_SECONDS = SHORT_TERM_TTL_SECONDS
REDIS_LAST_MESSAGES_KEY_TEMPLATE = "thread:{thread_id}:last_messages"
REDIS_MESSAGE_BUFFER_PREFIX = "langgraph:buffer:"  # Backward-compat constant 
REDIS_CHECKPOINT_PREFIX = "langgraph:checkpoint:"

# ============================================================================
# SAFETY CONTROLS (Task 5 — Rate Limits, Size Limits)
# ============================================================================

# Max characters allowed in a single user message (server-side hard cap).
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "4000"))

# Max characters for content stored in the Redis message buffer.
# Messages longer than this are truncated before storage.
MAX_STORED_CONTENT_CHARS = int(os.getenv("MAX_STORED_CONTENT_CHARS", "2000"))

# Metadata whitelist — only these keys are kept when storing messages.
METADATA_ALLOWED_KEYS = {"type", "options", "advisory_type", "recommendations", "visualizations"}
# Max serialized size (bytes) for the metadata dict after filtering.
MAX_METADATA_BYTES = int(os.getenv("MAX_METADATA_BYTES", "2048"))

# Basic per-thread rate limiting (Redis INCR + EXPIRE).
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "20"))  # max requests ...
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))  # ... per window
REDIS_RATE_LIMIT_KEY_TEMPLATE = "thread:{thread_id}:rate_limit"


def redis_connection_mode() -> str:
    """Return redis configuration mode for logs/health responses."""
    return "url" if REDIS_URL else "host_port"


def get_redis_url() -> str:
    """
    Return canonical Redis URL used by backend components.
    REDIS_URL takes precedence over host/port/password/db/ssl fallback vars.
    """
    if REDIS_URL:
        return REDIS_URL

    scheme = "rediss" if REDIS_SSL else "redis"
    password_segment = f":{quote(REDIS_PASSWORD, safe='')}@" if REDIS_PASSWORD else ""
    return f"{scheme}://{password_segment}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"


def get_redis_display_target() -> str:
    """Return non-sensitive Redis endpoint summary for startup logs."""
    if REDIS_URL:
        # Keep credentials out of logs while still showing configured endpoint shape.
        return "REDIS_URL (set)"
    return f"{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# ============================================================================
# AUTHENTICATION
# ============================================================================

JWT_SECRET = os.getenv("SECRET_KEY", "")
JWT_ALGORITHM = "HS256"

# ============================================================================
# SAIGE FARM GRAPH LLM PROVIDERS
# ============================================================================

# gemini (default, production) | grok (reserved — not wired yet)
SAIGE_LLM_PROVIDER = os.getenv("SAIGE_LLM_PROVIDER", "gemini").strip().lower() or "gemini"

# Single default chat/farm model for local + production (override via env only)
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_MODEL_NAME = (
    os.getenv("VERTEX_AI_MODEL")
    or os.getenv("GEMINI_MODEL")
    or _DEFAULT_GEMINI_MODEL
).strip() or _DEFAULT_GEMINI_MODEL
# Back-compat alias used by older references
GEMINI_FLASH_MODEL = GEMINI_MODEL_NAME

# Future Grok / xAI (do not use until provider implementation is enabled)
XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
GROK_MODEL = os.getenv("GROK_MODEL", "grok-2-latest").strip()

# Prefer SQL control-plane tables when reachable; JSON fallback otherwise
SAIGE_CONTROL_PLANE_SQL = os.getenv("SAIGE_CONTROL_PLANE_SQL", "true").lower() == "true"

# GCS media (required in multi-instance / Cloud Run). Local dir is fallback only.
SAIGE_MEDIA_GCS_BUCKET = os.getenv("SAIGE_MEDIA_GCS_BUCKET", "").strip()
SAIGE_MEDIA_GCS_PREFIX = os.getenv("SAIGE_MEDIA_GCS_PREFIX", "saige/media").strip().strip("/")
SAIGE_MEDIA_LOCAL_DIR = os.getenv("SAIGE_MEDIA_LOCAL_DIR", "").strip() or str(DEFAULT_MEDIA_DIR)


# ============================================================================
# PRODUCTION DETECTION
# ============================================================================

IS_PRODUCTION = bool(GCP_PROJECT)
LOG_FORMAT = "json" if IS_PRODUCTION else "text"

print(f"[Config] GCP Project: {GCP_PROJECT or 'Not set'}")
print(f"[Config] Firestore Available: {FIRESTORE_AVAILABLE}")
print(f"[Config] RAG Available: {RAG_AVAILABLE}")
print(f"[Config] SQL Sync Available: {SQL_SYNC_AVAILABLE}")
print(f"[Config] Redis Available: {REDIS_AVAILABLE}")
print(f"[Config] Redis Enabled: {REDIS_ENABLED}")
print(f"[Config] Redis Memory Fallback Allowed: {REDIS_ALLOW_MEMORY_FALLBACK}")
print(f"[Config] OFN Backend URL: {OFN_BACKEND_URL}")
print(f"[Config] RAG hybrid={RAG_HYBRID_ENABLED} rerank={RAG_RERANK_ENABLED} cache={RAG_CACHE_ENABLED}")
if REDIS_ENABLED:
    print(f"[Config] Redis Mode: {redis_connection_mode()}")
    print(f"[Config] Redis Target: {get_redis_display_target()}")
    if REDIS_SSL or (REDIS_URL and get_redis_url().startswith("rediss://")):
        print(f"[Config] Redis TLS cert policy: {REDIS_SSL_CERT_REQS}")
print(f"[Config] Production Mode: {IS_PRODUCTION}")
print("[Config] Saige architecture: supervisor farm graph")
print(f"[Config] LLM provider: {SAIGE_LLM_PROVIDER} (Gemini model: {GEMINI_MODEL_NAME})")
print(f"[Config] Control-plane SQL preferred: {SAIGE_CONTROL_PLANE_SQL}")
print(f"[Config] Media GCS bucket: {SAIGE_MEDIA_GCS_BUCKET or '(local fallback)'}")

# Compat: `from config import settings` then settings.GEMINI_MODEL_NAME, etc.
settings = sys.modules[__name__]
