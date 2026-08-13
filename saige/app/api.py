# --- app/api.py --- (Enhanced API for farm advisory system)
import os
import json
import logging
import time
import re
import base64
import struct
import asyncio
import threading
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, Request, Depends, Header
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from langgraph.types import Command

from config import (
    FRONTEND_URL, ALLOW_ALL_ORIGINS, IS_PRODUCTION, REDIS_ENABLED, SHORT_TERM_N,
    MAX_MESSAGE_CHARS, RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS,
    normalize_chat_product,
)
from graph import graph
from chat import run_chat, resume_hitl, iter_chat_events
from chat_history import chat_history
from message_buffer import message_buffer, get_last_n, push_message
from llm import llm
from saige_models import FollowUpEntityExtraction, MapIntentDetection
from app.dependencies import _check_rate_limit, get_current_user
from app.lifecycle import (
    _check_redis_health,
    _resolve_redis_manager,
    app_lifespan,
    logger,
)


def _is_missing_checkpoint_index_error(exc: Exception) -> bool:
    """Detect missing LangGraph Redis index errors from redisvl/redis exceptions."""
    error_str = str(exc).lower()
    return "no such index" in error_str and "checkpoint" in error_str


def safe_graph_stream(input_data, config, stream_mode="values"):
    """
    Yield events from graph.stream(), with fallback when Redis checkpoint indexes are missing.
    """
    try:
        primary_stream = graph.stream(input_data, config, stream_mode=stream_mode)
        for event in primary_stream:
            yield event
    except Exception as e:
        if _is_missing_checkpoint_index_error(e):
            print("[API] [WARN] Redis checkpoint indexes missing, using MemorySaver fallback for this request")
            from langgraph.checkpoint.memory import MemorySaver
            from graph import builder
            temp_graph = builder.compile(checkpointer=MemorySaver())
            for event in temp_graph.stream(input_data, config, stream_mode=stream_mode):
                yield event
        else:
            raise

# ============================================================================
# FASTAPI APP
# ============================================================================

app_kwargs = {"title": "Farm Advisory API", "version": "2.1.0"}
if IS_PRODUCTION:
    app_kwargs["docs_url"] = "/docs"
    app_kwargs["redoc_url"] = None
app_kwargs["lifespan"] = app_lifespan

app = FastAPI(**app_kwargs)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# GLOBAL EXCEPTION HANDLER
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An internal error occurred. Please try again later.",
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*",
        },
    )

# ============================================================================
# REQUEST LOGGING MIDDLEWARE
# ============================================================================

@app.middleware("http")
async def cors_and_logging_middleware(request: Request, call_next):
    # Handle preflight
    if request.method == "OPTIONS":
        return JSONResponse(
            content={},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Max-Age": "86400",
            },
        )
    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"{request.method} {request.url.path} unhandled_error={exc!r} duration={duration:.3f}s")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "*",
            },
        )
    duration = time.time() - start_time
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    logger.info(f"{request.method} {request.url.path} status={response.status_code} duration={duration:.3f}s")
    return response

# ============================================================================
# REQUEST MODELS
# ============================================================================

class ChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    thread_id: str = Field(..., min_length=1, max_length=128)
    business_id: Optional[str] = None  # from URL query param (?BusinessID=...)
    image_data: Optional[str] = None   # base64-encoded image for multimodal queries
    # Product namespace for chat history collections: "ofn" (default) | "loa"
    # Auth is shared; Firestore collections stay separate.
    product: Optional[str] = "ofn"
    # NOTE: people_id is NOT here — extracted from Bearer JWT by get_current_user()

    @field_validator("user_input")
    @classmethod
    def strip_user_input(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("user_input must not be empty or whitespace-only")
        return v

    @field_validator("product")
    @classmethod
    def normalize_product(cls, v: Optional[str]) -> str:
        return normalize_chat_product(v)


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


def _pcm_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1, bits: int = 16) -> bytes:
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16,
        1, channels, sample_rate,
        sample_rate * channels * bits // 8,
        channels * bits // 8,
        bits,
        b"data", data_size,
    )
    return header + pcm


@app.post("/tts")
async def text_to_speech(body: TTSRequest):
    """Convert text to speech using Google Cloud TTS (en-US-Studio-O)."""
    import requests as _req
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return JSONResponse(status_code=503, content={"error": "TTS not configured"})

    # -- Primary: Google Cloud TTS � en-US-Studio-O ---------------------------
    cloud_url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    cloud_payload = {
        "input": {"text": body.text},
        "voice": {"languageCode": "en-US", "name": "en-US-Studio-O"},
        "audioConfig": {"audioEncoding": "MP3"},
    }
    try:
        resp = _req.post(cloud_url, json=cloud_payload, timeout=15)
        resp.raise_for_status()
        audio_bytes = base64.b64decode(resp.json()["audioContent"])
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        logger.warning("[TTS] Cloud TTS failed, falling back to Gemini: %s", e)

    # -- Fallback: Gemini TTS � Zephyr (female) -------------------------------
    gemini_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash-preview-tts:generateContent?key={api_key}"
    )
    gemini_payload = {
        "contents": [{"parts": [{"text": body.text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Zephyr"}}},
        },
    }
    try:
        resp = _req.post(gemini_url, json=gemini_payload, timeout=30)
        resp.raise_for_status()
        inline = resp.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        wav_bytes = _pcm_to_wav(base64.b64decode(inline["data"]))
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        logger.error("[TTS] Gemini TTS error: %s", e)
        return JSONResponse(status_code=502, content={"error": "TTS generation failed"})


def _looks_like_new_question(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    if "?" in normalized:
        return True
    question_starters = (
        "how ", "what ", "which ", "when ", "where ", "why ",
        "can ", "should ", "is ", "are ", "do ", "does ", "will ",
    )
    if normalized.startswith(question_starters):
        return True
    intent_keywords = [
        "recommend", "advice", "weather", "forecast", "disease", "treatment",
        "breed", "fertilizer", "irrigation", "pest", "yield", "suitable",
    ]
    return len(normalized.split()) >= 4 and any(keyword in normalized for keyword in intent_keywords)


def _build_assessment_summary(current_issues, crops, location) -> str:
    summary_parts = [
        f"Farmer seeks assistance with: {', '.join(current_issues) if current_issues else 'general farm advice'}"
    ]
    if crops:
        summary_parts.append(f"Growing/Raising: {', '.join(crops)}")
    if location:
        summary_parts.append(f"Location: {location}")
    return " | ".join(summary_parts)


def _extract_soil_info(text: str) -> dict | None:
    raw_text = (text or "").strip()
    if not raw_text:
        return None
    lowered = raw_text.lower()
    soil_markers = [
        "soil test", "soil report", "ph", "ec", "electrical conductivity",
        "cec", "organic matter", "soil:water", "cmol",
    ]
    looks_like_soil_input = any(marker in lowered for marker in soil_markers)
    patterns = {
        "ph": r"\bph\b[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
        "electrical_conductivity": r"\b(?:electrical conductivity|ec)\b[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
        "cec": r"\bcec\b[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
        "organic_matter": r"\b(?:organic matter|om)\b[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
        "nitrogen": r"\b(?:available\s*)?(?:n|nitrogen)\b[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
        "phosphorus": r"\b(?:available\s*)?(?:p|phosphorus)\b[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
        "potassium": r"\b(?:available\s*)?(?:k|potassium)\b[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)",
    }
    extracted: dict = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            extracted[key] = float(match.group(1))
        except (TypeError, ValueError):
            continue
    if not looks_like_soil_input and len(extracted) < 2:
        return None
    if not looks_like_soil_input and not extracted:
        return None
    result = {"raw_text": raw_text}
    result.update(extracted)
    return result


def _buffer_messages_to_history(messages: list[dict]) -> list[str]:
    history: list[str] = []
    for msg in messages or []:
        role = str(msg.get("role") or "").strip().lower()
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            history.append(f"User: {content}")
        else:
            history.append(f"AI: {content}")
    return history


# ============================================================================
# HEALTH & READINESS ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "version": "2.1.0",
        "features": [
            "Supervisor farm graph",
            "Multi-specialist fan-out",
            "HITL proposals + execute",
            "Livestock/crop/weather RAG",
            "Chat persistence",
            "Thread management"
        ]
    }


@app.get("/health")
async def health_check(request: Request):
    llm_backend = "unavailable"
    try:
        from llm import get_farm_llm_backend
        llm_backend = get_farm_llm_backend()
    except Exception as e:
        llm_backend = f"unavailable:{e}"
    checks = {
        "architecture": "supervisor",
        "llm": llm_backend,
        "llm_provider": None,
        "control_plane": None,
        "redis": None,
        "firestore": None,
        "sql": None,
        "media": None,
    }
    try:
        from config import SAIGE_LLM_PROVIDER, SAIGE_MEDIA_GCS_BUCKET
        checks["llm_provider"] = SAIGE_LLM_PROVIDER
        checks["media"] = "gcs" if SAIGE_MEDIA_GCS_BUCKET else "local-fallback"
    except Exception:
        pass
    try:
        from db_control import table_exists
        checks["control_plane"] = "sql" if table_exists("SaigeProposals") else "json-fallback"
    except Exception:
        checks["control_plane"] = "unknown"
    if REDIS_ENABLED:
        try:
            redis_manager = _resolve_redis_manager(request)
            checks["redis"] = "healthy" if _check_redis_health(redis_manager)[0] else "unhealthy"
        except Exception:
            checks["redis"] = "unhealthy"
    try:
        checks["firestore"] = "healthy" if chat_history.health_check() else "unhealthy"
    except Exception:
        checks["firestore"] = "unhealthy"
    try:
        from config import DB_CONFIG
        import pymssql
        if DB_CONFIG.get("host"):
            conn = pymssql.connect(
                server=DB_CONFIG["host"], user=DB_CONFIG["user"],
                password=DB_CONFIG["password"], database=DB_CONFIG["database"],
                timeout=4, login_timeout=4,
            )
            conn.close()
            checks["sql"] = "healthy"
        else:
            checks["sql"] = "unconfigured"
    except Exception as e:
        checks["sql"] = f"unhealthy:{type(e).__name__}"
    return {
        "status": "healthy",
        "service": "farm-advisory-api",
        "architecture": "supervisor",
        "llm_farm_backend": llm_backend,
        "checks": checks,
    }


@app.get("/health/redis")
async def redis_health_check(request: Request):
    if not REDIS_ENABLED:
        return {"status": "disabled", "service": "redis", "message": "Redis is disabled by configuration"}
    redis_manager = _resolve_redis_manager(request)
    healthy, latency_ms, info = _check_redis_health(redis_manager)
    if healthy:
        return {"status": "healthy", "service": "redis", "latency_ms": round(latency_ms, 2), "mode": info.get("mode"), "target": info.get("target")}
    error_message = info.get("last_error") or "Redis unreachable"
    return JSONResponse(status_code=503, content={"status": "unhealthy", "service": "redis", "mode": info.get("mode"), "target": info.get("target"), "error": error_message})


@app.get("/ready")
async def readiness_check(request: Request):
    checks = {"graph": True, "jwt": False, "firestore": False}
    # JWT canary — fail loudly if SECRET_KEY cannot round-trip a token
    try:
        from jose import jwt as _jwt
        from config import JWT_SECRET, JWT_ALGORITHM
        from datetime import datetime, timedelta, timezone

        if not JWT_SECRET:
            checks["jwt"] = False
            checks["jwt_error"] = "SECRET_KEY missing"
        else:
            tok = _jwt.encode(
                {"sub": "ready-canary", "exp": datetime.now(timezone.utc) + timedelta(minutes=2)},
                JWT_SECRET,
                algorithm=JWT_ALGORITHM,
            )
            payload = _jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            checks["jwt"] = payload.get("sub") == "ready-canary"
    except Exception as e:
        checks["jwt"] = False
        checks["jwt_error"] = type(e).__name__
    try:
        checks["firestore"] = bool(chat_history.firestore_db)
    except Exception:
        checks["firestore"] = False
    if REDIS_ENABLED:
        redis_manager = _resolve_redis_manager(request)
        checks["redis"] = _check_redis_health(redis_manager)[0]
    critical = ["graph", "jwt"]
    try:
        from config import REDIS_ALLOW_MEMORY_FALLBACK
        redis_required = REDIS_ENABLED and not REDIS_ALLOW_MEMORY_FALLBACK
    except Exception:
        redis_required = REDIS_ENABLED
    if redis_required:
        critical.append("redis")
    critical_checks = {k: checks.get(k) for k in critical}
    all_ready = all(bool(v) for v in critical_checks.values())
    return JSONResponse(
        status_code=200 if all_ready else 503,
        content={"status": "ready" if all_ready else "not_ready", "checks": checks},
    )


@app.get("/health/firestore")
async def firestore_health():
    ok = chat_history.health_check()
    return JSONResponse(status_code=200 if ok else 503, content={"status": "healthy" if ok else "unhealthy", "service": "firestore"})


# ============================================================================
# INTENT HELPERS
# ============================================================================

_TOOL_ONLY_MAP_KW = (
    "zoom to", "zoom in to", "zoom into", "zoom the map", "zoom map",
    "zoom in on", "zoom over to", "zoom over", "zoom out",
    "go to zip", "fly to", "center on", "center map",
    "navigate to", "pan to", "jump to", "move map to", "focus on zip",
    "show zip", "show me on the map", "take me to zip", "go to the zip",
    "take me to", "bring the map", "show me where",
    "move over to", "move the map", "move to the",
)

# Matches "1365 Spring Street Medford", "242 Oak Ave Portland", etc.
_ADDRESS_RE = re.compile(
    r'\b\d{2,5}\b.{0,40}\b(street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|'
    r'lane|ln|way|court|ct|place|pl|highway|hwy|parkway|pkwy|route|rte)\b',
    re.IGNORECASE,
)

# Signals that a message *might* be a location/navigation query � gate for LLM fallback.
# Only fire the LLM call when at least one of these weaker hints is present.
_LOCATION_HINT_RE = re.compile(
    r'\b\d{5}\b'                                                        # zip code
    r'|\b(go|head|move|take|bring|drive|pull)\b.{0,25}\b(to|over)\b'  # nav verb + prep
    r'|\b\w{3,},\s+[A-Za-z]{2,}\b'                                     # "City, State"
    r'|\b(downtown|uptown|suburb|metro|area|region|district)\b',        # area descriptors
    re.IGNORECASE,
)

# Lazy singleton � built once on first LLM-fallback call
_map_intent_classifier = None


def _get_map_intent_classifier():
    global _map_intent_classifier
    if _map_intent_classifier is None:
        _map_intent_classifier = llm.with_structured_output(MapIntentDetection)
    return _map_intent_classifier


def _is_tool_only_intent(user_input: str) -> bool:
    """Layer 1+2: keyword match OR address regex � no LLM cost."""
    lum = user_input.lower()
    if any(k in lum for k in _TOOL_ONLY_MAP_KW):
        return True
    # Strip page/field context hints before address check
    clean = re.sub(r'\[(page|field)[^\]]*\]', '', lum, flags=re.IGNORECASE).strip()
    return bool(_ADDRESS_RE.search(clean))


def _classify_map_intent_llm(user_input: str) -> bool:
    """Layer 3: small structured-output LLM call, only when a location hint is present.
    ~300 ms cost; only fires when layers 1+2 both miss."""
    clean = re.sub(r'\[(page|field)[^\]]*\]', '', user_input, flags=re.IGNORECASE).strip()
    if not _LOCATION_HINT_RE.search(clean):
        return False
    try:
        result = _get_map_intent_classifier().invoke(
            f'User message: "{clean[:300]}"\n'
            "Is the user asking to navigate, zoom, pan, or center a map to a specific location?"
        )
        if result.is_map_navigation:
            print(f"[MapIntent-LLM] Classified as map navigation: {clean[:80]}")
        return result.is_map_navigation
    except Exception as _e:
        print(f"[MapIntent-LLM] Classification failed: {_e}")
        return False


# ============================================================================
# CHAT ENDPOINT
# ============================================================================

@app.post("/chat")
async def chat(
    request: ChatRequest,
    people_id: str = Depends(get_current_user),  # extracted from Bearer JWT
):
    """Main chat endpoint for farm advisory system."""
    business_id = request.business_id
    product = normalize_chat_product(request.product)
    if not business_id and people_id:
        try:
            from user_profile import get_primary_business_id as _get_biz_id
            business_id = _get_biz_id(people_id)
            if business_id:
                logger.info(f"[API] Auto-resolved business_id={business_id} for people_id={people_id}")
        except Exception as _biz_err:
            logger.debug("[API] business_id auto-resolve failed: %s", _biz_err)

    allowed, req_count = _check_rate_limit(request.thread_id)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "message": (
                    f"Too many requests. Please wait before sending another message. "
                    f"(limit: {RATE_LIMIT_MAX_REQUESTS} per {RATE_LIMIT_WINDOW_SECONDS}s)"
                ),
            },
        )

    result = run_chat(
        user_input=request.user_input,
        thread_id=request.thread_id,
        people_id=people_id,
        business_id=business_id,
        image_data=getattr(request, "image_data", None),
        product=product,
    )
    # success / interrupted / complete are expected client outcomes (HITL pauses as interrupted).
    status_code = 200 if result.get("status") in {"success", "interrupted", "complete"} else 500
    return JSONResponse(status_code=status_code, content=result)


# ============================================================================
# STREAMING CHAT ENDPOINT
# ============================================================================

@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    people_id: str = Depends(get_current_user),
):
    """SSE streaming: supervisor stages, specialist progress, tokens, then done."""
    allowed, req_count = _check_rate_limit(request.thread_id)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"status": "error", "message": f"Too many requests. (limit: {RATE_LIMIT_MAX_REQUESTS} per {RATE_LIMIT_WINDOW_SECONDS}s)"},
        )

    business_id = request.business_id
    product = normalize_chat_product(request.product)
    if not business_id and people_id:
        try:
            from user_profile import get_primary_business_id as _get_biz_id
            business_id = _get_biz_id(people_id)
        except Exception:
            business_id = None

    def _sse():
        for event in iter_chat_events(
            user_input=request.user_input,
            thread_id=request.thread_id,
            people_id=people_id,
            business_id=business_id,
            image_data=getattr(request, "image_data", None),
            product=product,
        ):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/threads")
async def list_threads(
    people_id: str = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
    business_id: Optional[str] = Query(default=None),
    product: str = Query(default="ofn"),
):
    """List chat threads for the authenticated user (product + optional business scope)."""
    product = normalize_chat_product(product)
    threads, next_cursor = chat_history.get_threads(
        people_id,
        limit=limit,
        cursor=cursor,
        business_id=business_id,
        product=product,
    )
    return {
        "threads": threads,
        "next_cursor": next_cursor,
        "product": product,
        "business_id": business_id,
    }


@app.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    people_id: str = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    business_id: Optional[str] = Query(default=None),
    product: str = Query(default="ofn"),
):
    """Get messages for a specific thread in the product collection."""
    product = normalize_chat_product(product)
    messages, next_cursor = chat_history.get_messages(
        people_id,
        thread_id,
        limit=limit,
        cursor=cursor,
        product=product,
        business_id=business_id,
    )
    if not messages and cursor is None:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {
        "thread_id": thread_id,
        "messages": messages,
        "next_cursor": next_cursor,
        "product": product,
        "business_id": business_id,
    }


@app.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    people_id: str = Depends(get_current_user),
    business_id: Optional[str] = Query(default=None),
    product: str = Query(default="ofn"),
):
    """Delete a chat thread belonging to the authenticated user."""
    product = normalize_chat_product(product)
    success = chat_history.delete_thread(
        people_id,
        thread_id,
        product=product,
        business_id=business_id,
    )
    if not success:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"status": "deleted", "thread_id": thread_id, "product": product}


# ============================================================================
# ANALYTICS ENDPOINT
# ============================================================================

@app.get("/analytics")
async def get_analytics(
    people_id: str = Depends(get_current_user),
    business_id: Optional[str] = Query(default=None),
    product: str = Query(default="ofn"),
):
    """Aggregate analytics for the authenticated user's chat sessions."""
    product = normalize_chat_product(product)
    data = chat_history.get_analytics(
        people_id,
        product=product,
        business_id=business_id,
    )
    if not data:
        return {"status": "no_data", "message": "No analytics data available."}
    return data


# ============================================================================
# FEEDBACK ENDPOINT  (data flywheel quality signal)
# ============================================================================

class FeedbackRequest(BaseModel):
    thread_id: str
    rating: int = Field(description="+1 (helpful) or -1 (not helpful)")
    comment: Optional[str] = Field(default=None, description="Optional free-text comment")


@app.post("/chat/feedback")
async def submit_chat_feedback(
    payload: FeedbackRequest,
    people_id: str = Depends(get_current_user),
):
    """
    Record a thumbs-up (+1) or thumbs-down (-1) on a Saige response.
    Applies the rating to the most recent anonymized learning extracted from
    that thread, so helpful answers reinforce the data flywheel and unhelpful
    ones are gradually downweighted.
    """
    if payload.rating not in (1, -1):
        return JSONResponse(status_code=400, content={"error": "rating must be +1 or -1"})
    try:
        from learning import learning_store as _learning_store
        _learning_store.record_feedback(payload.thread_id, payload.rating)
    except Exception as _fb_err:
        logger.warning("[Feedback] Could not apply rating: %s", _fb_err)
    logger.info("[Feedback] user=%s thread=%s rating=%+d", people_id, payload.thread_id, payload.rating)
    return {"status": "ok", "thread_id": payload.thread_id, "rating": payload.rating}


# ============================================================================
# COMPANION PLANTING ENDPOINTS
# ============================================================================

try:
    from companion_planting import (
        list_known_crops as _cp_list_known_crops,
        full_record as _cp_full_record,
        check_pair as _cp_check_pair,
        resolve_crop as _cp_resolve_crop,
    )
    _CP_AVAILABLE = True
except Exception as _cp_err:
    print(f"[API] companion_planting import failed: {_cp_err}")
    _CP_AVAILABLE = False


@app.get("/companion/crops")
async def companion_list_crops():
    """List every crop currently covered by the companion-planting database."""
    if not _CP_AVAILABLE:
        return {"status": "unavailable", "crops": []}
    return {"status": "ok", "crops": _cp_list_known_crops()}


@app.get("/companion/{crop}")
async def companion_get_crop(crop: str):
    """Get the full companion-planting record for a single crop (friends, foes, notes)."""
    if not _CP_AVAILABLE:
        return {"status": "unavailable"}
    rec = _cp_full_record(crop)
    if not rec:
        return {"status": "not_found", "crop": crop}
    return {"status": "ok", "crop": _cp_resolve_crop(crop), "record": rec}


@app.get("/companion/check/pair")
async def companion_check_pair(a: str, b: str):
    """Check whether two crops are good or bad companions."""
    if not _CP_AVAILABLE:
        return {"status": "unavailable"}
    result = _cp_check_pair(a, b)
    return {"status": "ok", "a": a, "b": b, "result": result}


# ============================================================================
# CROP NAMES (traditional / local)
# ============================================================================

try:
    from crop_names import lookup as _cn_lookup, list_all as _cn_list_all, resolve as _cn_resolve
    _CN_AVAILABLE = True
except Exception as _cn_err:
    print(f"[API] crop_names import failed: {_cn_err}")
    _CN_AVAILABLE = False


@app.get("/crop-names")
async def crop_names_list():
    if not _CN_AVAILABLE:
        return {"status": "unavailable", "crops": []}
    return {"status": "ok", "crops": _cn_list_all()}


@app.get("/crop-names/{name}")
async def crop_names_lookup(name: str):
    if not _CN_AVAILABLE:
        return {"status": "unavailable"}
    rec = _cn_lookup(name)
    if not rec:
        return {"status": "not_found", "name": name}
    return {"status": "ok", "query": name, "record": rec}


# ============================================================================
# WEATHER MITIGATION
# ============================================================================

try:
    from weather_mitigation import get_plan as _wm_get_plan, list_hazards as _wm_list_hazards
    _WM_AVAILABLE = True
except Exception as _wm_err:
    print(f"[API] weather_mitigation import failed: {_wm_err}")
    _WM_AVAILABLE = False


@app.get("/mitigation/hazards")
async def mitigation_list():
    if not _WM_AVAILABLE:
        return {"status": "unavailable", "hazards": []}
    return {"status": "ok", "hazards": _wm_list_hazards()}


@app.get("/mitigation/{hazard}")
async def mitigation_plan(hazard: str, phase: str = "imminent"):
    if not _WM_AVAILABLE:
        return {"status": "unavailable"}
    plan = _wm_get_plan(hazard, phase)
    if not plan:
        return {"status": "not_found", "hazard": hazard}
    return {"status": "ok", "plan": plan}


# ============================================================================
# REGION-SPECIFIC CROPS
# ============================================================================

try:
    from region_crops import recommend as _rc_recommend, list_climates as _rc_list_climates
    _RC_AVAILABLE = True
except Exception as _rc_err:
    print(f"[API] region_crops import failed: {_rc_err}")
    _RC_AVAILABLE = False


@app.get("/region/climates")
async def region_list_climates():
    if not _RC_AVAILABLE:
        return {"status": "unavailable", "climates": []}
    return {"status": "ok", "climates": _rc_list_climates()}


@app.get("/region/recommend")
async def region_recommend(
    climate: Optional[str] = None,
    zone: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    limit: int = 20,
):
    if not _RC_AVAILABLE:
        return {"status": "unavailable"}
    return _rc_recommend(climate=climate, zone=zone, lat=lat, lon=lon, limit=limit)


# ============================================================================
# SOIL CHALLENGES
# ============================================================================

try:
    from soil_challenges import assess as _sc_assess
    _SC_AVAILABLE = True
except Exception as _sc_err:
    print(f"[API] soil_challenges import failed: {_sc_err}")
    _SC_AVAILABLE = False


class SoilTestPayload(BaseModel):
    ph: Optional[float] = None
    organic_matter_pct: Optional[float] = None
    nitrogen_ppm: Optional[float] = None
    phosphorus_ppm: Optional[float] = None
    potassium_ppm: Optional[float] = None
    cec_meq: Optional[float] = None
    salinity_dsm: Optional[float] = None
    moisture_pct: Optional[float] = None
    bulk_density_gcc: Optional[float] = None
    sodium_pct_cec: Optional[float] = None
    crop: Optional[str] = None
    user_id: Optional[str] = None


@app.post("/soil/assess")
async def soil_assess(payload: SoilTestPayload):
    if not _SC_AVAILABLE:
        return {"status": "unavailable"}
    body = payload.model_dump(exclude_none=True)
    user_id = body.pop("user_id", None)
    result = _sc_assess(**body)
    try:
        from cross_links import subsidies_for_soil
        result["related_suggestions"] = subsidies_for_soil(result.get("challenges", []))
    except Exception:
        pass
    if user_id and result.get("status") == "ok":
        try:
            from history_store import record as _hist_record
            entry = _hist_record(user_id, "soil", {
                "inputs":    body,
                "headline":  result.get("headline"),
                "challenges": [
                    {"measure": c.get("measure"), "direction": c.get("direction"),
                     "severity": c.get("severity"), "value": c.get("value")}
                    for c in result.get("challenges", [])
                ],
            })
            result["history_id"] = entry["id"]
        except Exception as _e:
            print(f"[API] soil history record failed: {_e}")
    return result


# ============================================================================
# PEST DETECTION (vision LLM)
# ============================================================================

try:
    from pest_detection import detect_from_base64 as _pd_detect
    _PD_AVAILABLE = True
except Exception as _pd_err:
    print(f"[API] pest_detection import failed: {_pd_err}")
    _PD_AVAILABLE = False


class PestDetectPayload(BaseModel):
    image_base64: str
    notes: Optional[str] = ""
    user_id: Optional[str] = None


@app.post("/pest/detect")
async def pest_detect(payload: PestDetectPayload):
    if not _PD_AVAILABLE:
        return {"status": "unavailable"}
    result = _pd_detect(payload.image_base64, payload.notes or "")
    try:
        from cross_links import companions_for_pest
        if result.get("status") == "ok":
            result["related_suggestions"] = companions_for_pest(
                result.get("diagnosis", ""), result.get("category", "")
            )
    except Exception:
        pass
    if payload.user_id and result.get("status") == "ok":
        try:
            from history_store import record as _hist_record
            entry = _hist_record(payload.user_id, "pest", {
                "diagnosis":  result.get("diagnosis"),
                "confidence": result.get("confidence"),
                "category":   result.get("category"),
                "crop_identified": result.get("crop_identified"),
                "notes":      payload.notes or "",
            })
            result["history_id"] = entry["id"]
        except Exception as _e:
            print(f"[API] pest history record failed: {_e}")
    return result


# ============================================================================
# PRICE FORECAST
# ============================================================================

try:
    from price_forecast import forecast as _pf_forecast, list_commodities as _pf_list
    _PF_AVAILABLE = True
except Exception as _pf_err:
    print(f"[API] price_forecast import failed: {_pf_err}")
    _PF_AVAILABLE = False


@app.get("/price/commodities")
async def price_list():
    if not _PF_AVAILABLE:
        return {"status": "unavailable", "commodities": []}
    return {"status": "ok", "commodities": _pf_list()}


@app.get("/price/forecast/{commodity}")
async def price_forecast_endpoint(commodity: str, months_ahead: int = 6,
                                  user_id: Optional[str] = None):
    if not _PF_AVAILABLE:
        return {"status": "unavailable"}
    result = _pf_forecast(commodity, max(1, min(int(months_ahead or 6), 12)))
    try:
        from cross_links import insurance_for_commodity
        if result.get("status") == "ok":
            forecast = result.get("forecast", []) or []
            trend = None
            if forecast and result.get("recent_average") is not None:
                end = forecast[-1].get("expected")
                if isinstance(end, (int, float)):
                    ra = result["recent_average"]
                    if ra and end < ra * 0.95: trend = "down"
                    elif ra and end > ra * 1.05: trend = "up"
                    else: trend = "flat"
            result["related_suggestions"] = insurance_for_commodity(
                result.get("commodity", commodity), result.get("confidence"), trend
            )
    except Exception:
        pass
    if user_id and result.get("status") == "ok":
        try:
            from history_store import record as _hist_record
            entry = _hist_record(user_id, "price", {
                "commodity":      result.get("commodity"),
                "recent_average": result.get("recent_average"),
                "unit":           result.get("unit"),
                "confidence":     result.get("confidence"),
                "months_ahead":   months_ahead,
                "end_expected":   (result.get("forecast") or [{}])[-1].get("expected"),
            })
            result["history_id"] = entry["id"]
        except Exception as _e:
            print(f"[API] price history record failed: {_e}")
    return result


# ============================================================================
# SUBSIDIES
# ============================================================================

try:
    from subsidies import (
        search as _sb_search, get as _sb_get,
        list_categories as _sb_list_categories,
        list_countries as _sb_list_countries,
        ALL_PROGRAMS as _sb_programs,
    )
    _SB_AVAILABLE = True
except Exception as _sb_err:
    print(f"[API] subsidies import failed: {_sb_err}")
    _SB_AVAILABLE = False


@app.get("/subsidies/categories")
async def subsidies_categories(country: Optional[str] = None):
    if not _SB_AVAILABLE:
        return {"status": "unavailable", "categories": []}
    return {"status": "ok", "categories": _sb_list_categories(country=country)}


@app.get("/subsidies/countries")
async def subsidies_countries():
    if not _SB_AVAILABLE:
        return {"status": "unavailable", "countries": []}
    return {"status": "ok", "countries": _sb_list_countries()}


@app.get("/subsidies")
async def subsidies_search(
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 20,
):
    if not _SB_AVAILABLE:
        return {"status": "unavailable", "programs": []}
    return {"status": "ok", "programs": _sb_search(
        category=category, keyword=keyword, country=country, limit=limit,
    )}


@app.get("/subsidies/{program_id}")
async def subsidies_detail(program_id: str):
    if not _SB_AVAILABLE:
        return {"status": "unavailable"}
    p = _sb_get(program_id)
    if not p:
        return {"status": "not_found"}
    return {"status": "ok", "program": p}


# ============================================================================
# INSURANCE
# ============================================================================

try:
    from insurance import for_crop as _in_for_crop, list_crops as _in_list_crops, PRODUCTS as _in_products
    _IN_AVAILABLE = True
except Exception as _in_err:
    print(f"[API] insurance import failed: {_in_err}")
    _IN_AVAILABLE = False


@app.get("/insurance/crops")
async def insurance_list_crops():
    if not _IN_AVAILABLE:
        return {"status": "unavailable", "crops": []}
    return {"status": "ok", "crops": _in_list_crops()}


@app.get("/insurance/products")
async def insurance_list_products():
    if not _IN_AVAILABLE:
        return {"status": "unavailable", "products": []}
    return {"status": "ok", "products": _in_products}


@app.get("/insurance/for/{crop}")
async def insurance_for_crop(crop: str):
    if not _IN_AVAILABLE:
        return {"status": "unavailable"}
    return _in_for_crop(crop)


# ============================================================================
# PUSH NOTIFICATIONS
# ============================================================================

try:
    from push_notifications import (
        subscribe as _pn_subscribe, unsubscribe as _pn_unsubscribe,
        list_subscriptions as _pn_list, send_to as _pn_send_to,
        broadcast as _pn_broadcast, public_key as _pn_public_key,
        is_configured as _pn_is_configured,
    )
    _PN_AVAILABLE = True
except Exception as _pn_err:
    print(f"[API] push_notifications import failed: {_pn_err}")
    _PN_AVAILABLE = False


class PushSubscribePayload(BaseModel):
    user_id: str
    subscription: dict
    tags: Optional[List[str]] = None
    location: Optional[dict] = None  # {label, lat, lon}


class PushUnsubscribePayload(BaseModel):
    endpoint: str


class PushSendPayload(BaseModel):
    user_id: Optional[str] = None
    tag: Optional[str] = None
    title: str
    body: str
    url: Optional[str] = None


class PushTestPayload(BaseModel):
    user_id: str


@app.get("/push/public-key")
async def push_public_key():
    if not _PN_AVAILABLE:
        return {"configured": False, "public_key": ""}
    return {"configured": _pn_is_configured(), "public_key": _pn_public_key()}


@app.post("/push/subscribe")
async def push_subscribe(payload: PushSubscribePayload):
    if not _PN_AVAILABLE:
        return {"status": "unavailable"}
    return _pn_subscribe(payload.user_id, payload.subscription, payload.tags,
                         location=payload.location)


@app.post("/push/unsubscribe")
async def push_unsubscribe(payload: PushUnsubscribePayload):
    if not _PN_AVAILABLE:
        return {"status": "unavailable"}
    return _pn_unsubscribe(payload.endpoint)


@app.post("/push/send")
async def push_send(payload: PushSendPayload):
    if not _PN_AVAILABLE:
        return {"status": "unavailable"}
    if payload.user_id:
        return _pn_send_to(payload.user_id, payload.title, payload.body, payload.url, payload.tag)
    return _pn_broadcast(payload.title, payload.body, payload.url, payload.tag)


@app.post("/push/test")
async def push_test(payload: PushTestPayload):
    if not _PN_AVAILABLE:
        return {"status": "unavailable"}
    return _pn_send_to(
        payload.user_id,
        "OFN test notification",
        "If you see this, push notifications are working on this device.",
        "/saige/push",
    )


# ============================================================================
# SAIGE HISTORY (per-user trend cards)
# ============================================================================

try:
    import history_store as _hist
    _HIST_AVAILABLE = True
except Exception as _hist_err:
    print(f"[API] history_store import failed: {_hist_err}")
    _HIST_AVAILABLE = False


@app.get("/history/{user_id}")
async def history_list(user_id: str, type: Optional[str] = None, limit: int = 20):
    if not _HIST_AVAILABLE:
        return {"status": "unavailable", "entries": []}
    entries = _hist.list_for_user(user_id, entry_type=type,
                                  limit=max(1, min(int(limit or 20), 100)))
    return {"status": "ok", "entries": entries}


@app.delete("/history/{user_id}/{entry_id}")
async def history_delete(user_id: str, entry_id: str):
    if not _HIST_AVAILABLE:
        return {"status": "unavailable"}
    removed = _hist.delete_entry(user_id, entry_id)
    return {"status": "ok" if removed else "not_found"}


# ============================================================================
# PRECISION AG (field monitoring, satellite NDVI, alerts)
# ============================================================================

try:
    from precision_ag import (
        list_my_fields_tool as _pa_list_fields,
        get_field_analysis_tool as _pa_field_analysis,
        get_field_history_tool as _pa_field_history,
        get_field_alerts_tool as _pa_field_alerts,
    )
    _PA_AVAILABLE = True
except Exception as _pa_err:
    print(f"[API] precision_ag import failed: {_pa_err}")
    _PA_AVAILABLE = False


@app.get("/precision-ag/fields")
async def precision_ag_fields(people_id: str = Depends(get_current_user)):
    """List the authenticated user's satellite-monitored fields."""
    if not _PA_AVAILABLE:
        return {"status": "unavailable"}
    return {"status": "ok", "summary": _pa_list_fields.invoke({"people_id": people_id})}


@app.get("/precision-ag/fields/{field_id}/analysis")
async def precision_ag_field_analysis(
    field_id: int,
    people_id: str = Depends(get_current_user),
):
    """Latest satellite crop analysis (NDVI/EVI/SAVI + trend) for one field."""
    if not _PA_AVAILABLE:
        return {"status": "unavailable"}
    return {
        "status": "ok",
        "summary": _pa_field_analysis.invoke({"field_id": field_id, "people_id": people_id}),
    }


@app.get("/precision-ag/fields/{field_id}/history")
async def precision_ag_field_history(
    field_id: int,
    months: int = 6,
    people_id: str = Depends(get_current_user),
):
    """Vegetation-index time series over the last N months (default 6, max 24)."""
    if not _PA_AVAILABLE:
        return {"status": "unavailable"}
    return {
        "status": "ok",
        "summary": _pa_field_history.invoke({
            "field_id": field_id,
            "months": max(1, min(int(months or 6), 24)),
            "people_id": people_id,
        }),
    }


@app.get("/precision-ag/alerts")
async def precision_ag_alerts(
    field_id: int = 0,
    people_id: str = Depends(get_current_user),
):
    """Active precision-ag alerts. Pass field_id=0 (default) for all fields."""
    if not _PA_AVAILABLE:
        return {"status": "unavailable"}
    return {
        "status": "ok",
        "summary": _pa_field_alerts.invoke({"field_id": int(field_id or 0), "people_id": people_id}),
    }


@app.get("/precision-ag/dashboard")
async def precision_ag_dashboard(people_id: str = Depends(get_current_user)):
    """Structured dashboard summary: fields with latest NDVI, alert counts by severity,
    and irrigation urgency for the best-performing field."""
    if not _PA_AVAILABLE:
        return {"status": "unavailable", "fields": [], "alerts": {}, "irrigation_urgency": None}
    try:
        from precision_ag import _business_ids_for_people, _query, _BACKEND_URL
        import requests as _req

        biz_ids = _business_ids_for_people(people_id)
        if not biz_ids:
            return {"status": "ok", "fields": [], "alerts": {}, "irrigation_urgency": None}

        placeholders = ",".join(["%s"] * len(biz_ids))

        # Fields with their latest NDVI via the most recent Analysis + VegetationIndex
        field_rows = _query(
            f"SELECT f.FieldID, f.Name, f.CropType, f.FieldSizeHectares, f.MonitoringEnabled "
            f"FROM dbo.Field f "
            f"WHERE f.BusinessID IN ({placeholders}) AND f.DeletedAt IS NULL "
            f"ORDER BY f.Name",
            tuple(biz_ids),
        )

        fields_out = []
        best_field_id = None
        best_ndvi = None

        for fld in field_rows:
            fid = fld["fieldid"]
            # Latest analysis for this field
            an_rows = _query(
                "SELECT TOP 1 a.AnalysisID FROM dbo.Analysis a "
                "WHERE a.FieldID = %s ORDER BY a.AnalysisDate DESC",
                (fid,),
            )
            ndvi = None
            if an_rows:
                aid = an_rows[0]["analysisid"]
                vi_rows = _query(
                    "SELECT MeanValue FROM dbo.VegetationIndex "
                    "WHERE AnalysisID = %s AND IndexType = 'NDVI'",
                    (aid,),
                )
                if vi_rows and vi_rows[0].get("meanvalue") is not None:
                    try:
                        ndvi = round(float(vi_rows[0]["meanvalue"]), 3)
                    except (TypeError, ValueError):
                        pass

            entry = {
                "field_id": fid,
                "name": fld.get("name") or "Unnamed",
                "crop_type": fld.get("croptype") or None,
                "size_ha": float(fld["fieldsizehectares"]) if fld.get("fieldsizehectares") else None,
                "monitoring_enabled": bool(fld.get("monitoringenabled")),
                "ndvi": ndvi,
            }
            fields_out.append(entry)

            if ndvi is not None and (best_ndvi is None or ndvi > best_ndvi):
                best_ndvi = ndvi
                best_field_id = fid

        # Alert counts by severity (active/open only)
        sev_rows = _query(
            f"SELECT a.Severity, COUNT(*) AS cnt "
            f"FROM dbo.Alert a "
            f"JOIN dbo.Field f ON f.FieldID = a.FieldID "
            f"WHERE f.BusinessID IN ({placeholders}) "
            f"  AND (a.Status IS NULL OR a.Status <> 'resolved') "
            f"GROUP BY a.Severity",
            tuple(biz_ids),
        )
        alerts_by_sev: dict = {}
        for r in sev_rows:
            sev = (r.get("severity") or "unknown").lower()
            alerts_by_sev[sev] = int(r.get("cnt") or 0)

        # Irrigation urgency for the best field (calls OFN backend)
        irrigation_urgency = None
        if best_field_id:
            try:
                resp = _req.get(
                    f"{_BACKEND_URL}/api/fields/{best_field_id}/irrigation?days=7",
                    timeout=5,
                )
                if resp.ok:
                    irrigation_urgency = resp.json().get("urgency")
            except Exception:
                pass

        return {
            "status": "ok",
            "fields": fields_out,
            "alerts": alerts_by_sev,
            "irrigation_urgency": irrigation_urgency,
            "best_field_id": best_field_id,
        }
    except Exception as exc:
        print(f"[API] /precision-ag/dashboard error: {exc}")
        return {"status": "error", "fields": [], "alerts": {}, "irrigation_urgency": None}


# ============================================================================
# SAIGE DRAFTS (approval queue for action tools)
# ============================================================================

try:
    import actions as _saige_actions
    _ACTIONS_AVAILABLE = True
except Exception as _act_err:
    print(f"[API] saige.actions import failed: {_act_err}")
    _ACTIONS_AVAILABLE = False


def _commit_produce_draft(payload: dict) -> Optional[int]:
    """Insert a Produce row from an approved draft. Returns new ProduceID or None."""
    try:
        import pymssql
        from config import DB_CONFIG
    except Exception:
        return None
    conn = pymssql.connect(
        server=DB_CONFIG["host"], port=DB_CONFIG["port"],
        user=DB_CONFIG["user"], password=DB_CONFIG["password"],
        database=DB_CONFIG["database"], as_dict=True,
    )
    try:
        cur = conn.cursor()
        # Resolve ingredient and measurement IDs from names
        ingredient_id = None
        if payload.get("IngredientName"):
            cur.execute(
                "SELECT TOP 1 IngredientID FROM Ingredients WHERE IngredientName = %s",
                (str(payload["IngredientName"]),),
            )
            row = cur.fetchone()
            ingredient_id = (row or {}).get("ingredientid")
        measurement_id = None
        if payload.get("Measurement"):
            cur.execute(
                "SELECT TOP 1 MeasurementID FROM MeasurementLookup "
                "WHERE Measurement = %s OR MeasurementAbbreviation = %s",
                (str(payload["Measurement"]), str(payload["Measurement"])),
            )
            row = cur.fetchone()
            measurement_id = (row or {}).get("measurementid")
        cur.execute(
            """
            INSERT INTO Produce (IngredientID, Quantity, MeasurementID, WholesalePrice,
                                 RetailPrice, BusinessID, AvailableDate)
            OUTPUT INSERTED.ProduceID
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(ingredient_id) if ingredient_id else None,
                float(payload.get("Quantity") or 0) or None,
                int(measurement_id) if measurement_id else None,
                float(payload.get("WholesalePrice")) if payload.get("WholesalePrice") else None,
                float(payload.get("RetailPrice")) if payload.get("RetailPrice") else None,
                int(payload.get("BusinessID") or 0) or None,
                payload.get("AvailableDate") or None,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return int((row or {}).get("produceid") or 0) or None
    except Exception as e:
        print(f"[API] commit_produce_draft failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _commit_event_draft(payload: dict) -> Optional[int]:
    try:
        import pymssql
        from config import DB_CONFIG
    except Exception:
        return None
    conn = pymssql.connect(
        server=DB_CONFIG["host"], port=DB_CONFIG["port"],
        user=DB_CONFIG["user"], password=DB_CONFIG["password"],
        database=DB_CONFIG["database"], as_dict=True,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO OFNEvents (BusinessID, PeopleID, EventName, EventDescription,
                EventStartDate, EventEndDate, EventLocationName,
                EventLocationCity, EventLocationState,
                IsPublished, IsFree, RegistrationRequired)
            OUTPUT INSERTED.EventID
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(payload.get("BusinessID") or 0) or None,
                str(payload.get("PeopleID")) if payload.get("PeopleID") else None,
                payload.get("EventName"),
                payload.get("EventDescription") or None,
                payload.get("EventStartDate") or None,
                payload.get("EventEndDate") or None,
                payload.get("EventLocationName") or None,
                payload.get("EventLocationCity") or None,
                payload.get("EventLocationState") or None,
                1,  # publish on approve
                int(payload.get("IsFree") or 0),
                int(payload.get("RegistrationRequired") or 0),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return int((row or {}).get("eventid") or 0) or None
    except Exception as e:
        print(f"[API] commit_event_draft failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _commit_blog_draft(payload: dict) -> Optional[int]:
    try:
        import pymssql
        import re as _re
        from config import DB_CONFIG
    except Exception:
        return None
    conn = pymssql.connect(
        server=DB_CONFIG["host"], port=DB_CONFIG["port"],
        user=DB_CONFIG["user"], password=DB_CONFIG["password"],
        database=DB_CONFIG["database"], as_dict=True,
    )
    try:
        cur = conn.cursor()
        title = str(payload.get("Title") or "").strip()
        slug = _re.sub(r"[^a-z0-9\s-]", "", title.lower())
        slug = _re.sub(r"\s+", "-", slug)[:200]
        cur.execute(
            """
            INSERT INTO blog (BusinessID, Title, Slug, Content, IsPublished,
                              ShowOnDirectory, ShowOnWebsite, PublishedAt, CreatedAt, UpdatedAt)
            OUTPUT INSERTED.BlogID
            VALUES (%s, %s, %s, %s, 1, 1, 1, GETUTCDATE(), GETUTCDATE(), GETUTCDATE())
            """,
            (
                int(payload.get("BusinessID") or 0) or None,
                title,
                slug,
                payload.get("Content") or "",
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return int((row or {}).get("blogid") or 0) or None
    except Exception as e:
        print(f"[API] commit_blog_draft failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


class DraftUpdatePayload(BaseModel):
    payload: dict


class DraftRejectPayload(BaseModel):
    reason: Optional[str] = None


class ResumeRequest(BaseModel):
    thread_id: str
    decision: str = Field(description="approve | edit | reject")
    proposal_id: Optional[str] = None
    edits: Optional[Dict[str, Any]] = None
    decisions: Optional[List[Dict[str, Any]]] = None
    product: Optional[str] = "ofn"
    business_id: Optional[str] = None


@app.post("/resume")
async def saige_resume(
    request: ResumeRequest,
    people_id: str = Depends(get_current_user),
):
    """HITL resume — approve / edit / reject pending proposals."""
    result = resume_hitl(
        thread_id=request.thread_id,
        people_id=people_id,
        decision=request.decision,
        proposal_id=request.proposal_id,
        edits=request.edits,
        decisions=request.decisions,
        product=normalize_chat_product(request.product),
        business_id=request.business_id,
    )
    return result



@app.get("/proposals")
async def saige_proposals_list(
    business_id: Optional[str] = None,
    status: Optional[str] = "pending",
    people_id: str = Depends(get_current_user),
):
    """List HITL proposals (local JSON store until SQL DDL applied)."""
    from proposals_store import list_proposals

    rows = list_proposals(people_id=people_id, business_id=business_id, status=status)
    return {"status": "ok", "proposals": rows}


@app.get("/proposals/{proposal_id}/events")
async def saige_proposal_events(
    proposal_id: str,
    people_id: str = Depends(get_current_user),
):
    """HITL audit trail for a proposal."""
    from proposals_store import get_proposal, list_proposal_events

    row = get_proposal(proposal_id)
    if not row:
        return JSONResponse({"status": "not_found"}, status_code=404)
    if row.get("people_id") and str(row.get("people_id")) not in {"", str(people_id)}:
        # Soft check — allow same business later; block obvious cross-user
        if str(row.get("people_id")) != str(people_id):
            return JSONResponse({"status": "forbidden"}, status_code=403)
    return {"status": "ok", "proposal_id": proposal_id, "events": list_proposal_events(proposal_id)}


class ProposalDecidePayload(BaseModel):
    decision: str = Field(description="approve | edit | reject")
    thread_id: Optional[str] = None
    edits: Optional[Dict[str, Any]] = None
    product: Optional[str] = "ofn"
    business_id: Optional[str] = None


@app.post("/proposals/{proposal_id}/decide")
async def saige_proposal_decide(
    proposal_id: str,
    body: ProposalDecidePayload,
    people_id: str = Depends(get_current_user),
):
    """Approve/edit/reject a proposal — aliases resume when thread_id known."""
    from proposals_store import get_proposal

    row = get_proposal(proposal_id)
    if not row:
        return JSONResponse({"status": "not_found"}, status_code=404)
    thread_id = body.thread_id or row.get("thread_id")
    if not thread_id:
        return JSONResponse({"status": "error", "message": "thread_id required"}, status_code=400)
    return resume_hitl(
        thread_id=thread_id,
        people_id=people_id,
        decision=body.decision,
        proposal_id=proposal_id,
        edits=body.edits,
        product=normalize_chat_product(body.product),
        business_id=body.business_id or row.get("business_id"),
    )


@app.get("/plans")
async def saige_plans_list(
    business_id: Optional[str] = None,
    people_id: str = Depends(get_current_user),
):
    from plans_store import list_plans

    rows = list_plans(business_id=business_id, people_id=people_id)
    return {"status": "ok", "plans": rows}


@app.get("/plans/{plan_id}")
async def saige_plan_get(plan_id: str, people_id: str = Depends(get_current_user)):
    from plans_store import get_plan

    row = get_plan(plan_id)
    if not row:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return {"status": "ok", "plan": row}


@app.get("/monitoring/runs")
async def saige_monitoring_runs(
    business_id: Optional[str] = None,
    people_id: str = Depends(get_current_user),
):
    from monitoring_store import list_runs

    return {"status": "ok", "runs": list_runs(business_id=business_id)}


@app.post("/attach")
async def saige_attach(
    request: Request,
    people_id: str = Depends(get_current_user),
):
    """Upload scout/media image to GCS (local fallback only when bucket unset)."""
    import base64

    from media_storage import store_bytes

    try:
        body = await request.json()
    except Exception:
        body = {}
    image_b64 = (body or {}).get("image_data") or (body or {}).get("image") or ""
    business_id = str((body or {}).get("business_id") or "unknown")
    content_type = str((body or {}).get("content_type") or "image/jpeg")
    if not image_b64:
        return JSONResponse({"status": "error", "message": "image_data required"}, status_code=400)
    if "," in image_b64[:80]:
        image_b64 = image_b64.split(",", 1)[1]
    try:
        raw = base64.b64decode(image_b64)
    except Exception:
        return JSONResponse({"status": "error", "message": "invalid base64"}, status_code=400)
    if len(raw) > 12 * 1024 * 1024:
        return JSONResponse({"status": "error", "message": "image too large (max 12MB)"}, status_code=413)
    try:
        result = store_bytes(
            data=raw,
            people_id=people_id,
            business_id=business_id,
            content_type=content_type,
        )
        # Optional vision scout analysis
        if (body or {}).get("scout") in (True, "true", "1", 1):
            from vision_scout import scout_from_bytes

            result["scout"] = scout_from_bytes(
                raw,
                crop_hint=str((body or {}).get("crop_hint") or ""),
                people_id=people_id,
                business_id=business_id,
            )
        return result
    except Exception as e:
        logger.exception("[attach] failed: %s", e)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/saige/drafts")
async def saige_drafts_list(
    business_id: int = 0,
    people_id: str = Depends(get_current_user),
):
    """List the caller's pending Saige drafts. If business_id is provided,
    also include drafts scoped to that business (co-workers can see and
    approve the same business's drafts)."""
    if not _ACTIONS_AVAILABLE:
        return {"status": "unavailable", "drafts": []}
    drafts = _saige_actions.list_pending_drafts(people_id, int(business_id or 0) or None)
    return {"status": "ok", "drafts": drafts}


@app.get("/saige/drafts/{draft_id}")
async def saige_draft_get(draft_id: int, people_id: str = Depends(get_current_user)):
    if not _ACTIONS_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    draft = _saige_actions.get_draft(int(draft_id))
    if not draft:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return {"status": "ok", "draft": draft}


@app.post("/saige/drafts/{draft_id}/update")
async def saige_draft_update(
    draft_id: int,
    body: DraftUpdatePayload,
    people_id: str = Depends(get_current_user),
):
    if not _ACTIONS_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    ok = _saige_actions.update_draft_payload(int(draft_id), body.payload or {})
    if not ok:
        return JSONResponse({"status": "not_pending_or_missing"}, status_code=404)
    return {"status": "ok", "draft": _saige_actions.get_draft(int(draft_id))}


@app.post("/saige/drafts/{draft_id}/approve")
async def saige_draft_approve(draft_id: int, people_id: str = Depends(get_current_user)):
    """Validate + commit the draft to its real resource table, then mark approved."""
    if not _ACTIONS_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    draft = _saige_actions.get_draft(int(draft_id))
    if not draft:
        return JSONResponse({"status": "not_found"}, status_code=404)
    if draft.get("Status") != "pending":
        return JSONResponse(
            {"status": "already_processed", "current": draft.get("Status")},
            status_code=409,
        )
    dtype = draft.get("DraftType")
    payload = draft.get("Payload") or {}
    new_id: Optional[int] = None
    if dtype == "produce_listing":
        new_id = _commit_produce_draft(payload)
    elif dtype == "event":
        new_id = _commit_event_draft(payload)
    elif dtype == "blog_post":
        new_id = _commit_blog_draft(payload)
    else:
        return JSONResponse(
            {"status": "unsupported_type", "draft_type": dtype},
            status_code=400,
        )
    if not new_id:
        return JSONResponse(
            {"status": "commit_failed", "draft_type": dtype},
            status_code=500,
        )
    _saige_actions.mark_approved(int(draft_id), new_id)
    return {
        "status": "approved",
        "draft_id": int(draft_id),
        "draft_type": dtype,
        "resource_id": new_id,
    }


@app.post("/saige/drafts/{draft_id}/reject")
async def saige_draft_reject(
    draft_id: int,
    body: DraftRejectPayload | None = None,
    people_id: str = Depends(get_current_user),
):
    if not _ACTIONS_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    reason = (body.reason if body else None)
    ok = _saige_actions.mark_rejected(int(draft_id), reason)
    if not ok:
        return JSONResponse({"status": "not_pending_or_missing"}, status_code=404)
    return {"status": "rejected", "draft_id": int(draft_id)}


# ============================================================================
# WEATHER ALERTS (signal engine that drives push)
# ============================================================================

try:
    import weather_alerts as _wx_alerts
    _WXA_AVAILABLE = True
except Exception as _wxa_err:
    print(f"[API] weather_alerts import failed: {_wxa_err}")
    _WXA_AVAILABLE = False


class WeatherAlertPayload(BaseModel):
    dry_run: bool = False
    days_ahead: int = 2
    user_id: Optional[str] = None


@app.post("/alerts/proactive/run")
async def alerts_proactive_run(
    business_id: str = "",
    people_id: str = Depends(get_current_user),
):
    """Scheduler-friendly proactive digest (plans / monitoring / weather nudge)."""
    from proactive import run_proactive_digest

    return run_proactive_digest(business_id=business_id, people_id=people_id)


# ============================================================================
# CHEF DASHBOARD (recipes, par levels, seasonal, provenance)
# ============================================================================

try:
    import chef as _chef
    _CHEF_AVAILABLE = True
except Exception as _chef_err:
    print(f"[API] saige.chef import failed: {_chef_err}")
    _CHEF_AVAILABLE = False


class ChefRecipeItemPayload(BaseModel):
    ingredient: str
    qty: float = 0.0
    unit: str = ""
    preferred_business_id: Optional[int] = None


class ChefRecipeCreatePayload(BaseModel):
    business_id: int
    name: str
    items: List[ChefRecipeItemPayload] = []
    portion_yield: int = 1
    menu_price: Optional[float] = None


class ChefParUpsertPayload(BaseModel):
    business_id: int
    ingredient_name: str
    unit: str = ""
    on_hand: float = 0.0
    par_level: float = 0.0
    reorder_at: float = 0.0
    preferred_business_id: Optional[int] = None


@app.get("/chef/recipes")
async def chef_recipes_list(
    business_id: int,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return {"status": "unavailable", "recipes": []}
    recipes = _chef.list_recipes_for_business(int(business_id))
    return {"status": "ok", "recipes": recipes}


@app.post("/chef/recipes")
async def chef_recipes_create(
    body: ChefRecipeCreatePayload,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    items_json = json.dumps([i.model_dump() for i in body.items])
    result = _chef.save_recipe_tool.invoke({
        "name":          body.name,
        "items_json":    items_json,
        "portion_yield": int(body.portion_yield or 1),
        "menu_price":    float(body.menu_price or 0),
        "business_id":   int(body.business_id),
    })
    return {"status": "ok", "message": result}


@app.get("/chef/recipes/{recipe_id}/items")
async def chef_recipe_items(
    recipe_id: int,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return {"status": "unavailable", "items": []}
    return {"status": "ok", "items": _chef.list_recipe_items(int(recipe_id))}


@app.get("/chef/recipes/{recipe_id}/cost")
async def chef_recipe_cost(
    recipe_id: int,
    business_id: int,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    recipes = _chef.list_recipes_for_business(int(business_id))
    target = next((r for r in recipes if int(r.get("recipeid") or 0) == int(recipe_id)), None)
    if not target:
        return JSONResponse({"status": "not_found"}, status_code=404)
    result = _chef.cost_recipe_tool.invoke({
        "recipe_name": target.get("name") or "",
        "business_id": int(business_id),
    })
    return {"status": "ok", "report": result}


@app.delete("/chef/recipes/{recipe_id}")
async def chef_recipe_delete(
    recipe_id: int,
    business_id: int,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    ok = _chef.delete_recipe(int(recipe_id), int(business_id))
    if not ok:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return {"status": "ok"}


@app.get("/chef/par")
async def chef_par_list(
    business_id: int,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return {"status": "unavailable", "par": []}
    return {"status": "ok", "par": _chef.list_par_for_business(int(business_id))}


@app.post("/chef/par")
async def chef_par_upsert(
    body: ChefParUpsertPayload,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    msg = _chef.set_par_tool.invoke({
        "ingredient_name":       body.ingredient_name,
        "unit":                  body.unit or "",
        "on_hand":               float(body.on_hand or 0),
        "par_level":             float(body.par_level or 0),
        "reorder_at":            float(body.reorder_at or 0),
        "preferred_business_id": int(body.preferred_business_id or 0),
        "business_id":           int(body.business_id),
    })
    return {"status": "ok", "message": msg}


@app.delete("/chef/par/{par_id}")
async def chef_par_delete(
    par_id: int,
    business_id: int,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    ok = _chef.delete_par(int(par_id), int(business_id))
    if not ok:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return {"status": "ok"}


@app.get("/chef/seasonal")
async def chef_seasonal(
    state: str = "",
    category: str = "",
    business_id: int = 0,
    limit: int = 20,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    report = _chef.seasonal_menu_tool.invoke({
        "state":       state or "",
        "category":    category or "",
        "business_id": int(business_id or 0),
        "limit":       int(limit or 20),
    })
    return {"status": "ok", "report": report}


@app.get("/chef/provenance")
async def chef_provenance(
    ingredients: str,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    cards = _chef.provenance_cards_tool.invoke({
        "ingredient_names": ingredients or "",
    })
    return {"status": "ok", "cards": cards}


@app.post("/chef/restock-draft")
async def chef_restock_draft(
    business_id: int,
    people_id: str = Depends(get_current_user),
):
    if not _CHEF_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    report = _chef.draft_restock_order_tool.invoke({
        "business_id": int(business_id),
    })
    return {"status": "ok", "report": report}


# ============================================================================
# PAIRSLEY � food-service agent (restaurants / chefs / kitchens)
# ============================================================================

try:
    import pairsley as _pairsley
    _PAIRSLEY_AVAILABLE = True
except Exception as _pairsley_err:
    print(f"[API] pairsley import failed: {_pairsley_err}")
    _PAIRSLEY_AVAILABLE = False


class PairsleyChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    thread_id: str = Field(..., min_length=1, max_length=128)
    business_id: Optional[int] = None

    @field_validator("user_input")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("user_input must not be empty")
        return v


@app.post("/pairsley/chat")
async def pairsley_chat(
    request: PairsleyChatRequest,
    people_id: str = Depends(get_current_user),
):
    """One chat turn with Pairsley. Rate-limited per thread (same policy as Saige)."""
    if not _PAIRSLEY_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    allowed, req_count = _check_rate_limit(request.thread_id)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"status": "error", "message": f"Too many requests ({req_count}/{RATE_LIMIT_MAX_REQUESTS} in {RATE_LIMIT_WINDOW_SECONDS}s)."},
        )
    result = _pairsley.respond(
        user_input=request.user_input,
        thread_id=request.thread_id,
        user_id=people_id,
        business_id=request.business_id,
    )
    return result


@app.get("/pairsley/threads")
async def pairsley_threads(
    people_id: str = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
):
    if not _PAIRSLEY_AVAILABLE:
        return {"threads": [], "next_cursor": None}
    threads, next_cursor = _pairsley.list_threads(people_id, limit=limit, cursor=cursor)
    return {"threads": threads, "next_cursor": next_cursor}


@app.get("/pairsley/threads/{thread_id}/messages")
async def pairsley_thread_messages(
    thread_id: str,
    people_id: str = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
):
    if not _PAIRSLEY_AVAILABLE:
        return {"thread_id": thread_id, "messages": [], "next_cursor": None}
    messages, next_cursor = _pairsley.get_messages(people_id, thread_id, limit=limit, cursor=cursor)
    if not messages and cursor is None:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"thread_id": thread_id, "messages": messages, "next_cursor": next_cursor}


@app.delete("/pairsley/threads/{thread_id}")
async def pairsley_thread_delete(
    thread_id: str,
    people_id: str = Depends(get_current_user),
):
    if not _PAIRSLEY_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    ok = _pairsley.delete_thread(people_id, thread_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"status": "deleted", "thread_id": thread_id}


# ============================================================================
# ROSEMARIE � artisan-producer agent (mills / bakers / cheesemakers / etc.)
# ============================================================================

try:
    import rosemarie as _rosemarie
    _ROSEMARIE_AVAILABLE = True
except Exception as _rosemarie_err:
    print(f"[API] rosemarie import failed: {_rosemarie_err}")
    _ROSEMARIE_AVAILABLE = False


class RosemarieChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    thread_id: str = Field(..., min_length=1, max_length=128)
    business_id: Optional[int] = None

    @field_validator("user_input")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("user_input must not be empty")
        return v


@app.post("/rosemarie/chat")
async def rosemarie_chat(
    request: RosemarieChatRequest,
    people_id: str = Depends(get_current_user),
):
    """One chat turn with Rosemarie. Rate-limited per thread."""
    if not _ROSEMARIE_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    allowed, req_count = _check_rate_limit(request.thread_id)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"status": "error", "message": f"Too many requests ({req_count}/{RATE_LIMIT_MAX_REQUESTS} in {RATE_LIMIT_WINDOW_SECONDS}s)."},
        )
    result = _rosemarie.respond(
        user_input=request.user_input,
        thread_id=request.thread_id,
        user_id=people_id,
        business_id=request.business_id,
    )
    return result


@app.get("/rosemarie/threads")
async def rosemarie_threads(
    people_id: str = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
):
    if not _ROSEMARIE_AVAILABLE:
        return {"threads": [], "next_cursor": None}
    threads, next_cursor = _rosemarie.list_threads(people_id, limit=limit, cursor=cursor)
    return {"threads": threads, "next_cursor": next_cursor}


@app.get("/rosemarie/threads/{thread_id}/messages")
async def rosemarie_thread_messages(
    thread_id: str,
    people_id: str = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
):
    if not _ROSEMARIE_AVAILABLE:
        return {"thread_id": thread_id, "messages": [], "next_cursor": None}
    messages, next_cursor = _rosemarie.get_messages(people_id, thread_id, limit=limit, cursor=cursor)
    if not messages and cursor is None:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"thread_id": thread_id, "messages": messages, "next_cursor": next_cursor}


@app.delete("/rosemarie/threads/{thread_id}")
async def rosemarie_thread_delete(
    thread_id: str,
    people_id: str = Depends(get_current_user),
):
    if not _ROSEMARIE_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    ok = _rosemarie.delete_thread(people_id, thread_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"status": "deleted", "thread_id": thread_id}


# ============================================================================
# CASSIA � customer success / account-setup agent
# ============================================================================

try:
    import cassia as _cassia
    _CASSIA_AVAILABLE = True
except Exception as _cassia_err:
    print(f"[API] cassia import failed: {_cassia_err}")
    _CASSIA_AVAILABLE = False


class CassiaChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    thread_id:  str = Field(..., min_length=1, max_length=128)
    business_id: Optional[int] = None

    @field_validator("user_input")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("user_input must not be empty")
        return v


@app.post("/cassia/chat")
async def cassia_chat(
    request: CassiaChatRequest,
    people_id: str = Depends(get_current_user),
):
    """One chat turn with Cassia. Rate-limited per thread."""
    if not _CASSIA_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    allowed, req_count = _check_rate_limit(request.thread_id)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"status": "error", "message": f"Too many requests ({req_count}/{RATE_LIMIT_MAX_REQUESTS} in {RATE_LIMIT_WINDOW_SECONDS}s)."},
        )
    result = _cassia.respond(
        user_input=request.user_input,
        thread_id=request.thread_id,
        user_id=people_id,
        business_id=request.business_id,
    )
    return result


class CassiaCheckoutRequest(BaseModel):
    tier:         str   = "starter"
    categories:   list  = []
    lineItems:    list  = []
    monthlyTotal: float = 0.0
    annualPrice:  int   = 0
    successUrl:   str   = ""
    cancelUrl:    str   = ""
    businessId:   Optional[int] = None


_STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
_OFN_BASE_URL      = os.getenv("OFN_BASE_URL", "https://oatmealfarmnetwork.com")

# Fallback annual prices when Stripe price IDs are not configured
_CASSIA_TIER_AMOUNTS: dict = {
    "starter":      700_00,   # cents
    "professional": 1_700_00,
    "enterprise":   4_100_00,
}
_CASSIA_TIER_NAMES: dict = {
    "starter":      "OFN Starter Annual",
    "professional": "OFN Professional Annual",
    "enterprise":   "OFN Enterprise Annual",
}


@app.post("/cassia/checkout")
async def cassia_checkout(
    req: CassiaCheckoutRequest,
    people_id: str = Depends(get_current_user),
):
    """Create a Stripe Checkout Session for an OFN annual subscription chosen via Cassia.

    Looks up the Stripe price ID from the SubscriptionLevels table (keyed by tier name).
    Falls back to a one-time `payment` session using the canonical annual amount when no
    pre-configured price ID exists.  Returns { stripeUrl } or { stripeUrl: null } for the
    free/hobby tier so the frontend can skip directly to the account page."""
    tier = (req.tier or "starter").lower().strip()

    # Free plan � no Stripe session needed
    if req.monthlyTotal == 0 and req.annualPrice == 0:
        return {"stripeUrl": None}

    if not _STRIPE_SECRET_KEY:
        # Stripe not configured � let the frontend bypass to account
        return {"stripeUrl": None}

    try:
        import stripe as _stripe
        _stripe.api_key = _STRIPE_SECRET_KEY

        annual_cents = (
            req.annualPrice * 100
            if req.annualPrice > 0
            else _CASSIA_TIER_AMOUNTS.get(tier, int(req.monthlyTotal * 12 * 100))
        )
        tier_label = _CASSIA_TIER_NAMES.get(tier, f"OFN {tier.capitalize()} Annual")

        success_url = req.successUrl or f"{_OFN_BASE_URL}/cassia?subscribed=1"
        cancel_url  = req.cancelUrl  or f"{_OFN_BASE_URL}/cassia"

        # Attempt to find a pre-configured annual Stripe price via SubscriptionLevels
        price_id: Optional[str] = None
        try:
            from database import SessionLocal
            from sqlalchemy import text as _text
            with SessionLocal() as _db:
                row = _db.execute(
                    _text(
                        "SELECT StripeAPIID, StripeAPIIDTest FROM SubscriptionLevels "
                        "WHERE LOWER(SubscriptionTier) = :t OR LOWER(SubscriptionTitle) LIKE :tl"
                    ),
                    {"t": tier, "tl": f"%{tier}%"},
                ).fetchone()
                if row:
                    from app.routers.platform_settings import get_stripe_config
                    cfg = get_stripe_config(_db)
                    is_test = bool(cfg.get("StripeTestMode", True))
                    price_id = row[1] if is_test else row[0]
        except Exception:
            pass  # Fall through to one-time payment below

        if price_id:
            # Recurring subscription session using a pre-configured Stripe price
            metadata = {"tier": tier, "people_id": str(people_id)}
            if req.businessId:
                metadata["business_id"] = str(req.businessId)
            session = _stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                metadata=metadata,
                success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
            )
        else:
            # One-time annual payment (no pre-configured Stripe price required)
            metadata = {"tier": tier, "people_id": str(people_id)}
            if req.businessId:
                metadata["business_id"] = str(req.businessId)
            session = _stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "quantity": 1,
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": annual_cents,
                        "product_data": {
                            "name": tier_label,
                            "description": f"Annual OFN platform subscription � {', '.join(req.categories[:4]) or 'all features'}",
                        },
                    },
                }],
                metadata=metadata,
                success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
            )

        return {"stripeUrl": session.url}

    except Exception as e:
        print(f"[cassia_checkout] Stripe error: {e}")
        # Non-fatal � let the frontend handle missing stripeUrl gracefully
        return {"stripeUrl": None}


_STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_CASSIA_WEBHOOK_SECRET", "")


@app.post("/cassia/checkout/webhook")
async def cassia_checkout_webhook(request: Request):
    """Stripe webhook � fires after a Cassia-initiated checkout.session.completed.

    Verifies the Stripe signature, then:
      1. Updates Business.SubscriptionTier in SQL.
      2. Writes plan_tier to the org_profiles Firestore doc (via Cassia's ChatHistory).
    Returns 200 immediately so Stripe does not retry."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        import stripe as _stripe
        _stripe.api_key = _STRIPE_SECRET_KEY

        if _STRIPE_WEBHOOK_SECRET:
            event = _stripe.Webhook.construct_event(payload, sig_header, _STRIPE_WEBHOOK_SECRET)
        else:
            # Dev-mode fallback � no signature check (never do this in production)
            event = json.loads(payload)
    except Exception as e:
        print(f"[cassia_webhook] signature/parse error: {e}")
        return Response(status_code=400)

    if event.get("type") != "checkout.session.completed":
        return Response(status_code=200)

    session   = event.get("data", {}).get("object", {})
    metadata  = session.get("metadata") or {}
    tier      = (metadata.get("tier") or "starter").lower().strip()
    biz_id    = metadata.get("business_id")

    if not biz_id:
        return Response(status_code=200)

    biz_id_int = int(biz_id)

    # 1. Update SQL
    try:
        from database import SessionLocal
        from sqlalchemy import text as _text
        with SessionLocal() as _db:
            _db.execute(
                _text("UPDATE Business SET SubscriptionTier = :t WHERE BusinessID = :b"),
                {"t": tier, "b": biz_id_int},
            )
            _db.commit()
    except Exception as e:
        print(f"[cassia_webhook] SQL update error: {e}")

    # 2. Update Firestore org_profiles
    if _CASSIA_AVAILABLE:
        try:
            _cassia.cassia_chat_history.save_org_memory_profile(
                str(biz_id_int), {"plan_tier": tier}
            )
        except Exception as e:
            print(f"[cassia_webhook] Firestore update error: {e}")

    return Response(status_code=200)


@app.get("/cassia/threads")
async def cassia_threads(
    people_id: str = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
):
    if not _CASSIA_AVAILABLE:
        return {"threads": [], "next_cursor": None}
    threads, next_cursor = _cassia.list_threads(people_id, limit=limit, cursor=cursor)
    return {"threads": threads, "next_cursor": next_cursor}


@app.get("/cassia/threads/{thread_id}/messages")
async def cassia_thread_messages(
    thread_id: str,
    people_id: str = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
):
    if not _CASSIA_AVAILABLE:
        return {"thread_id": thread_id, "messages": [], "next_cursor": None}
    messages, next_cursor = _cassia.get_messages(people_id, thread_id, limit=limit, cursor=cursor)
    if not messages and cursor is None:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"thread_id": thread_id, "messages": messages, "next_cursor": next_cursor}


@app.delete("/cassia/threads/{thread_id}")
async def cassia_thread_delete(
    thread_id: str,
    people_id: str = Depends(get_current_user),
):
    if not _CASSIA_AVAILABLE:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    ok = _cassia.delete_thread(people_id, thread_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"status": "deleted", "thread_id": thread_id}


# ============================================================================
# WEATHER ALERTS � scheduled job + per-user dry-run
# ============================================================================

try:
    from weather_alerts import run as _run_weather_alerts
    _WEATHER_ALERTS_EP_AVAILABLE = True
except Exception as _wae_err:
    print(f"[API] weather_alerts endpoint import failed: {_wae_err}")
    _WEATHER_ALERTS_EP_AVAILABLE = False

_CRON_SECRET = os.getenv("CRON_SECRET", "")

_FARM_DIGEST_AVAILABLE = False
try:
    from farm_digest import run_digest as _run_farm_digest
    _FARM_DIGEST_AVAILABLE = True
except Exception as _fde:
    print(f"[API] farm_digest unavailable: {_fde}")


@app.post("/cron/farm-digest")
async def trigger_farm_digest(
    dry_run: bool = Query(False),
    business_id: Optional[int] = Query(None, alias="BusinessID"),
    x_cron_secret: str = Header(default="", alias="X-Cron-Secret"),
):
    """Personalized farm-health digest.
    Scans all agent_briefings Firestore docs, generates an LLM insight for each
    business with new precision-ag alerts, and pushes it to the farmer's device(s).
    Secured by X-Cron-Secret header. Trigger from Cloud Scheduler (daily)."""
    if _CRON_SECRET and x_cron_secret != _CRON_SECRET:
        return JSONResponse(status_code=403, content={"error": "Unauthorized"})
    if not _FARM_DIGEST_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Farm digest unavailable"},
        )
    fs_db = getattr(chat_history, "firestore_db", None)
    result = _run_farm_digest(
        firestore_db=fs_db,
        dry_run=dry_run,
        business_id_filter=business_id,
    )
    logger.info(
        "[Digest] Farm digest: scanned=%d sent=%d skipped=%d errors=%d dry_run=%s",
        result.get("scanned", 0),
        result.get("sent", 0),
        result.get("skipped", 0),
        result.get("errors", 0),
        dry_run,
    )
    return result


@app.post("/alerts/weather/run")
async def trigger_weather_alerts(
    dry_run: bool = Query(False),
    x_cron_secret: str = Header(default="", alias="X-Cron-Secret"),
):
    """Full weather-alert scan across all subscribed users.
    Secured by X-Cron-Secret header. Trigger from Cloud Scheduler every hour."""
    if _CRON_SECRET and x_cron_secret != _CRON_SECRET:
        return JSONResponse(status_code=403, content={"error": "Unauthorized"})
    if not _WEATHER_ALERTS_EP_AVAILABLE:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Weather alerts unavailable"})
    result = _run_weather_alerts(dry_run=dry_run)
    logger.info(
        f"[Alerts] Weather scan: scanned={result.get('scanned', 0)}, "
        f"sent={result.get('sent', 0)}, dry_run={dry_run}"
    )
    return result


@app.post("/alerts/weather/check/{user_id}")
async def check_user_weather_alerts(
    user_id: str,
    people_id: str = Depends(get_current_user),
    days_ahead: int = Query(default=2, ge=1, le=5),
):
    """Dry-run weather check for the authenticated user's saved push-notification
    locations. Returns what alerts *would* be sent without actually sending them."""
    if people_id != user_id:
        return JSONResponse(status_code=403, content={"error": "Can only check your own alerts"})
    if not _WEATHER_ALERTS_EP_AVAILABLE:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Weather alerts unavailable"})
    result = _run_weather_alerts(dry_run=True, user_id=user_id, days_ahead=days_ahead)
    return result


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"[API] Starting Farm Advisory API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)