# --- api.py --- (Enhanced API for farm advisory system)
import os
import json
import logging
import time
import re
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from langgraph.types import Command

from config import (
    FRONTEND_URL, ALLOW_ALL_ORIGINS, IS_PRODUCTION, REDIS_ENABLED, SHORT_TERM_N,
    MAX_MESSAGE_CHARS, RATE_LIMIT_ENABLED, RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS, REDIS_RATE_LIMIT_KEY_TEMPLATE,
)
from graph import graph
from chat_history import chat_history
from message_buffer import message_buffer, get_last_n, push_message
from redis_client import RedisClientManager, get_redis_manager
from llm import llm
from models import FollowUpEntityExtraction


def _is_missing_checkpoint_index_error(exc: Exception) -> bool:
    """Detect missing LangGraph Redis index errors from redisvl/redis exceptions."""
    error_str = str(exc).lower()
    return "no such index" in error_str and "checkpoint" in error_str


def safe_graph_stream(input_data, config, stream_mode="values"):
    """
    Yield events from graph.stream(), with fallback when Redis checkpoint indexes are missing.

    Important: graph.stream() errors can occur during iteration (not only at creation time),
    so this wrapper must iterate and yield inside the try/except.
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
# STRUCTURED LOGGING
# ============================================================================

logger = logging.getLogger("farm_advisory")
logger.setLevel(logging.INFO)

if IS_PRODUCTION:
    handler = logging.StreamHandler()

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                "severity": record.levelname,
                "message": record.getMessage(),
                "timestamp": self.formatTime(record),
                "logger": record.name,
            }
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_entry)

    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
else:
    logging.basicConfig(level=logging.INFO)


def _resolve_redis_manager(request: Request | None = None) -> RedisClientManager:
    """Get shared Redis manager from app state, with singleton fallback."""
    if request is not None:
        app_manager = getattr(request.app.state, "redis_manager", None)
        if app_manager is not None:
            return app_manager
    return get_redis_manager()


def _check_redis_health(redis_manager: RedisClientManager) -> tuple[bool, float, dict]:
    """Ping Redis and return health tuple (is_healthy, latency_ms, connection_info)."""
    start = time.perf_counter()
    is_healthy = redis_manager.ping()
    latency_ms = (time.perf_counter() - start) * 1000
    info = redis_manager.connection_info()
    return is_healthy, latency_ms, info


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Initialize and close shared Redis client pools for the API lifecycle."""
    app.state.redis_manager = None
    app.state.redis_text_client = None
    app.state.redis_binary_client = None

    if REDIS_ENABLED:
        redis_manager = get_redis_manager()
        app.state.redis_manager = redis_manager
        app.state.redis_text_client = redis_manager.get_client(decode_responses=True)
        app.state.redis_binary_client = redis_manager.get_client(decode_responses=False)

        if app.state.redis_text_client is not None:
            message_buffer.set_client(app.state.redis_text_client)

        healthy, latency_ms, info = _check_redis_health(redis_manager)
        if healthy:
            logger.info(
                f"[API] Shared Redis manager ready (mode={info.get('mode')}, target={info.get('target', 'n/a')}, latency_ms={latency_ms:.2f})"
            )
        else:
            logger.error(
                f"[API] Shared Redis manager unhealthy at startup (mode={info.get('mode')}, target={info.get('target', 'n/a')}): {info.get('last_error', 'unknown error')}"
            )
    else:
        logger.info("[API] Redis is disabled by configuration")

    try:
        yield
    finally:
        redis_manager = getattr(app.state, "redis_manager", None)
        if redis_manager is not None:
            redis_manager.close()
            logger.info("[API] Shared Redis manager pools closed")

# ============================================================================
# FASTAPI APP
# ============================================================================

app_kwargs = {"title": "Farm Advisory API", "version": "2.1.0"}
if IS_PRODUCTION:
    app_kwargs["docs_url"] = "/docs"
    app_kwargs["redoc_url"] = None
app_kwargs["lifespan"] = app_lifespan

app = FastAPI(**app_kwargs)

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
        }
    )

# ============================================================================
# REQUEST LOGGING MIDDLEWARE
# ============================================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} "
        f"status={response.status_code} duration={duration:.3f}s"
    )
    return response

# ============================================================================
# CORS
# ============================================================================

allowed_origins = [FRONTEND_URL]
if ALLOW_ALL_ORIGINS:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print(f"[API] CORS enabled for origins: {allowed_origins}")

# ============================================================================
# REQUEST MODELS
# ============================================================================

class ChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    thread_id: str = Field(..., min_length=1, max_length=128)
    user_id: str = Field(default="anonymous", max_length=128)

    @field_validator("user_input")
    @classmethod
    def strip_user_input(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("user_input must not be empty or whitespace-only")
        return v


def _looks_like_new_question(text: str) -> bool:
    """Heuristic guard to avoid treating fresh questions as slot-only answers."""
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
    """Build a compact summary so completed threads can route without re-assessment."""
    summary_parts = [
        f"Farmer seeks assistance with: {', '.join(current_issues) if current_issues else 'general farm advice'}"
    ]
    if crops:
        summary_parts.append(f"Growing/Raising: {', '.join(crops)}")
    if location:
        summary_parts.append(f"Location: {location}")
    return " | ".join(summary_parts)


def _extract_soil_info(text: str) -> dict | None:
    """Best-effort parser for common soil test metrics in free-text user input."""
    raw_text = (text or "").strip()
    if not raw_text:
        return None

    lowered = raw_text.lower()
    soil_markers = [
        "soil test",
        "soil report",
        "ph",
        "ec",
        "electrical conductivity",
        "cec",
        "organic matter",
        "soil:water",
        "cmol",
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

    # Avoid false positives from generic numeric messages.
    if not looks_like_soil_input and len(extracted) < 2:
        return None
    if not looks_like_soil_input and not extracted:
        return None

    result = {"raw_text": raw_text}
    result.update(extracted)
    return result


def _buffer_messages_to_history(messages: list[dict]) -> list[str]:
    """Convert short-term Redis messages to graph history format."""
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
# RATE LIMITER (Task 5 — per-thread rate limiting via Redis INCR + EXPIRE)
# ============================================================================

def _check_rate_limit(thread_id: str) -> tuple[bool, int]:
    """
    Check per-thread rate limit using Redis.
    Returns (allowed, current_count).
    If Redis is unavailable the request is always allowed (fail-open).
    """
    if not RATE_LIMIT_ENABLED or not REDIS_ENABLED:
        return True, 0

    client = message_buffer.client  # reuse the shared text client
    if client is None:
        return True, 0  # fail-open when Redis is down

    key = REDIS_RATE_LIMIT_KEY_TEMPLATE.format(thread_id=thread_id)
    try:
        pipe = client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        results = pipe.execute()
        current_count = int(results[0])
        return current_count <= RATE_LIMIT_MAX_REQUESTS, current_count
    except Exception as e:
        logger.warning(f"[RateLimit] Redis error (fail-open): {e}")
        return True, 0


# ============================================================================
# HEALTH & READINESS ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """API health check"""
    return {
        "status": "healthy",
        "version": "2.1.0",
        "features": [
            "User-driven assessment",
            "Hybrid routing (keyword + LLM)",
            "Livestock RAG integration",
            "Separate advisory nodes",
            "Chat persistence",
            "Thread management"
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "farm-advisory-api"}


@app.get("/health/redis")
async def redis_health_check(request: Request):
    """
    Redis connectivity health endpoint.
    - 200 disabled: Redis intentionally turned off
    - 200 healthy: Redis reachable
    - 503 unhealthy: Redis enabled but unreachable
    """
    if not REDIS_ENABLED:
        return {
            "status": "disabled",
            "service": "redis",
            "message": "Redis is disabled by configuration",
        }

    redis_manager = _resolve_redis_manager(request)
    healthy, latency_ms, info = _check_redis_health(redis_manager)

    if healthy:
        return {
            "status": "healthy",
            "service": "redis",
            "latency_ms": round(latency_ms, 2),
            "mode": info.get("mode"),
            "target": info.get("target"),
        }

    error_message = info.get("last_error") or "Redis unreachable"
    logger.error(
        f"[API] /health/redis unhealthy (mode={info.get('mode')}, target={info.get('target', 'n/a')}): {error_message}"
    )
    return JSONResponse(
        status_code=503,
        content={
            "status": "unhealthy",
            "service": "redis",
            "mode": info.get("mode"),
            "target": info.get("target"),
            "error": error_message,
        },
    )


@app.get("/ready")
async def readiness_check(request: Request):
    """Readiness probe - checks that critical services are connectable."""
    checks = {"graph": True}
    
    # Check Firestore
    try:
        if chat_history.firestore_db:
            checks["firestore"] = True
        else:
            checks["firestore"] = False
    except Exception:
        checks["firestore"] = False
    
    # Check Redis if enabled
    if REDIS_ENABLED:
        redis_manager = _resolve_redis_manager(request)
        checks["redis"] = _check_redis_health(redis_manager)[0]
    
    # All critical services must be ready (graph is always required)
    critical_checks = {k: v for k, v in checks.items() if k in ["graph", "redis"]}
    all_ready = all(critical_checks.values()) if critical_checks else True
    
    return JSONResponse(
        status_code=200 if all_ready else 503,
        content={"status": "ready" if all_ready else "not_ready", "checks": checks}
    )


@app.get("/health/firestore")
async def firestore_health():
    """Deep health check — performs an actual Firestore read/write/delete cycle."""
    ok = chat_history.health_check()
    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if ok else "unhealthy",
            "service": "firestore",
        },
    )

# ============================================================================
# CHAT ENDPOINT
# ============================================================================

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint for farm advisory system.

    Features:
    - User-driven assessment (starts with open question)
    - Hybrid routing (keyword matching + LLM fallback)
    - Specialized advisory nodes (livestock/crops/mixed)
    - Livestock RAG integration
    - Chat persistence to Firestore
    - Task 5: input size cap, per-thread rate limiting, bounded storage
    """
    # --- Task 5: per-thread rate limit ---
    allowed, req_count = _check_rate_limit(request.thread_id)
    if not allowed:
        logger.warning(
            f"[RateLimit] Thread {request.thread_id} exceeded limit "
            f"({req_count}/{RATE_LIMIT_MAX_REQUESTS} in {RATE_LIMIT_WINDOW_SECONDS}s)"
        )
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

    turn_start = time.time()
    config = {"configurable": {"thread_id": request.thread_id}}
    last_n = get_last_n(request.thread_id, SHORT_TERM_N)
    short_term_history = _buffer_messages_to_history(last_n)

    # Save user message to chat history (Firestore - long-term)
    chat_history.save_message(
        user_id=request.user_id,
        thread_id=request.thread_id,
        role="user",
        content=request.user_input,
    )
    
    # Add to message buffer (Redis - fast short-term context)
    push_message(
        thread_id=request.thread_id,
        message={
            "role": "user",
            "content": request.user_input,
        },
    )

    # Check if the thread is already waiting for an answer
    # Handle Redis index creation errors gracefully (indexes are created on first write)
    try:
        state = graph.get_state(config)
    except Exception as state_error:
        # If Redis indexes don't exist yet, they'll be created on first put during streaming
        # For now, treat as new conversation (empty state)
        error_str = str(state_error)
        if "No such index" in error_str or "checkpoint" in error_str.lower():
            print(f"[API] [INFO] Redis indexes will be created on first write, treating as new conversation")
            # Create a minimal state object to continue
            class EmptyState:
                def __init__(self):
                    self.next = []
                    self.values = {}
                    self.tasks = None
            state = EmptyState()
        else:
            raise state_error
    
    # Early stage detection based on user input (for better UX)
    early_stage = "default"
    user_input_lower = request.user_input.lower()
    weather_keywords = ["weather", "temperature", "forecast", "rain", "climate", "temperature"]
    if any(kw in user_input_lower for kw in weather_keywords):
        early_stage = "weather"
    elif any(kw in user_input_lower for kw in ["cattle", "cow", "sheep", "goat", "pig", "chicken", "livestock", "animal", "breed"]):
        early_stage = "livestock"
    elif any(kw in user_input_lower for kw in ["crop", "plant", "wheat", "rice", "corn", "tomato", "guava", "orange"]):
        early_stage = "crops"
    
    if state.next:
        # Resume the existing conversation
        print(f"[API] Resuming conversation for thread {request.thread_id}")
        events = safe_graph_stream(Command(resume=request.user_input), config, stream_mode="values")
    else:
        # Check if this is a follow-up question in a completed conversation
        existing_state = state.values if state.values else {}
        has_completed_conversation = existing_state.get("assessment_summary") and not state.next
        
        if has_completed_conversation:
            # This is a follow-up question - intelligently extract entities and preserve context
            print(f"[API] Follow-up question in thread {request.thread_id} - extracting entities and preserving context")
            
            # Use LLM to intelligently extract entities from follow-up input
            try:
                entity_extractor = llm.with_structured_output(FollowUpEntityExtraction)
                extraction_prompt = f"""Analyze this follow-up input from a farmer and extract entities:

Previous conversation context:
- Crops/Animals: {', '.join(existing_state.get('crops', [])) if existing_state.get('crops') else 'None'}
- Location: {existing_state.get('location', 'Not provided')}
- Previous issue: {existing_state.get('current_issues', ['general'])[-1] if existing_state.get('current_issues') else 'general'}

User's new input: "{request.user_input}"

Determine:
1. Is this an answer to a previous question? (location, crop type, animal type, farm size, etc.)
2. What entities are mentioned? Extract:
   - Location (city, state, region like "Hayward, California", "San Jose", "North region")
   - Crops/plants (e.g., "wheat", "tomato", "orange", "guava")
   - Animals/livestock (e.g., "cattle", "chicken", "sheep")
   - Farm size (e.g., "5 acres", "10 hectares")
3. Is this a new question or an answer?

Examples:
- "hayward, california" → is_answer: true, entity_type: "location", extracted_location: "Hayward, California"
- "cattle" → is_answer: true, entity_type: "animal", extracted_animals: ["cattle"]
- "wheat" → is_answer: true, entity_type: "crop", extracted_crops: ["wheat"]
- "how often should I water" → is_new_question: true, is_answer: false
- "5 acres" → is_answer: true, entity_type: "farm_size", extracted_farm_size: "5 acres"
"""

                extracted = entity_extractor.invoke(extraction_prompt)
                print(f"[API] Entity extraction: is_answer={extracted.is_answer}, entity_type={extracted.entity_type}, is_new_question={extracted.is_new_question}")
                
            except Exception as e:
                print(f"[API] Entity extraction error: {e} - falling back to simple detection")
                extracted = None
            
            # Keep conversation continuity instead of resetting into assessment mode.
            existing_history = short_term_history or (existing_state.get("history", []) if existing_state else [])
            new_history = (existing_history + [f"User: {request.user_input}"])[-SHORT_TERM_N:]
            parsed_soil_info = _extract_soil_info(request.user_input)

            # Build update: preserve conversation state, clear response fields for regeneration.
            update = {
                "history": new_history,
                "diagnosis": None,
                "recommendations": [],
                # Let routing recalculate type from current query/context.
                "advisory_type": None,
            }
            
            # Intelligently handle extracted entities
            is_entity_only_answer = (
                bool(extracted and extracted.is_answer)
                and bool(extracted and not extracted.is_new_question)
                and not _looks_like_new_question(request.user_input)
            )

            if is_entity_only_answer:
                # This is an answer to a previous question - extract and set entities
                print(f"[API] Processing answer: entity_type={extracted.entity_type}")
                applied_entity_update = False
                
                if extracted.entity_type == "location" and extracted.extracted_location:
                    update["location"] = extracted.extracted_location
                    applied_entity_update = True
                    print(f"[API] Extracted location: {extracted.extracted_location}")
                elif extracted.entity_type == "crop" and extracted.extracted_crops:
                    existing_crops = existing_state.get("crops", [])
                    update["crops"] = existing_crops + [c for c in extracted.extracted_crops if c not in existing_crops]
                    applied_entity_update = True
                    print(f"[API] Extracted crops: {extracted.extracted_crops}")
                elif extracted.entity_type == "animal" and extracted.extracted_animals:
                    existing_crops = existing_state.get("crops", [])
                    update["crops"] = existing_crops + [a for a in extracted.extracted_animals if a not in existing_crops]
                    applied_entity_update = True
                    print(f"[API] Extracted animals: {extracted.extracted_animals}")
                elif extracted.entity_type == "farm_size" and extracted.extracted_farm_size:
                    update["farm_size"] = extracted.extracted_farm_size
                    applied_entity_update = True
                    print(f"[API] Extracted farm size: {extracted.extracted_farm_size}")
                
                # Preserve existing context
                if existing_state.get("crops") and not update.get("crops"):
                    update["crops"] = existing_state["crops"]
                if existing_state.get("location") and not update.get("location"):
                    update["location"] = existing_state["location"]
                if existing_state.get("current_issues"):
                    # Keep only latest issue to reduce stale multi-turn noise.
                    update["current_issues"] = existing_state["current_issues"][-1:]

                # If no concrete entity was extracted, keep this answer as new issue detail.
                if not applied_entity_update:
                    issue_details = list(existing_state.get("current_issues", []))
                    detail = request.user_input.strip()
                    if detail and detail not in issue_details:
                        issue_details.append(detail)
                    update["current_issues"] = issue_details[-3:]
                    print("[API] No concrete entity extracted; appended answer detail to current_issues")
            else:
                # This is a new question - set as current issue
                update["current_issues"] = [request.user_input]
                
                # Preserve existing context if available
                if existing_state.get("crops"):
                    update["crops"] = existing_state["crops"]
                if existing_state.get("location"):
                    update["location"] = existing_state["location"]

            # Capture soil test metrics when user shares report values.
            if parsed_soil_info:
                existing_soil_info = existing_state.get("soil_info")
                merged_soil_info = dict(existing_soil_info) if isinstance(existing_soil_info, dict) else {}
                merged_soil_info.update(parsed_soil_info)
                update["soil_info"] = merged_soil_info
                print(f"[API] Parsed soil info keys: {list(parsed_soil_info.keys())}")

            # Keep assessment marked complete so follow-ups route directly to advisory.
            merged_issues = update.get("current_issues", existing_state.get("current_issues", []))
            merged_crops = update.get("crops", existing_state.get("crops", []))
            merged_location = update.get("location", existing_state.get("location"))
            update["assessment_summary"] = _build_assessment_summary(
                merged_issues,
                merged_crops,
                merged_location,
            )

            events = safe_graph_stream(update, config, stream_mode="values")
        else:
            # Start a brand new conversation with user's first message
            print(f"[API] Starting new conversation for thread {request.thread_id}")
            print(f"[API] First message: {request.user_input[:100]}...")
            initial_history = (short_term_history + [f"User: {request.user_input}"])[-SHORT_TERM_N:] if short_term_history else [f"User: {request.user_input}"]
            events = safe_graph_stream({"history": initial_history}, config, stream_mode="values")

    # Collect all events to ensure state is fully updated
    events_list = []
    for event in events:
        events_list.append(event)
        print(f"[API] Event keys: {list(event.keys())}")

    # Get the latest state after streaming
    # Handle Redis index creation errors gracefully (indexes should exist after streaming)
    try:
        final_state = graph.get_state(config)
    except Exception as state_error:
        # If Redis indexes still don't exist, create a minimal state
        error_str = str(state_error)
        if "No such index" in error_str or "checkpoint" in error_str.lower():
            print(f"[API] [WARN] Redis indexes not available, using empty state")
            class EmptyState:
                def __init__(self):
                    self.next = []
                    self.values = {}
                    self.tasks = None
            final_state = EmptyState()
        else:
            raise state_error
    print(f"[API] Final state - Next nodes: {final_state.next}")
    print(f"[API] Final state - Has tasks: {len(final_state.tasks) if final_state.tasks else 0}")
    
    # Determine processing stage for UI feedback
    final_values = final_state.values if final_state.values else {}
    
    # Start with early detection, then refine based on actual state
    processing_stage = early_stage if early_stage != "default" else "assessment"
    
    if final_state.next:
        # Still processing - determine stage from next nodes (more accurate)
        next_nodes = list(final_state.next)
        if "assessment_node" in next_nodes:
            processing_stage = "assessment"
        elif "routing_node" in next_nodes:
            processing_stage = "routing"
        elif "weather_advisory_node" in next_nodes:
            processing_stage = "weather"
        elif "livestock_advisory_node" in next_nodes:
            processing_stage = "livestock"
        elif "crop_advisory_node" in next_nodes:
            processing_stage = "crops"
        elif "mixed_advisory_node" in next_nodes:
            processing_stage = "mixed"
    else:
        # Completed - use advisory_type to show final stage (most accurate)
        advisory_type = final_values.get("advisory_type", "unknown")
        if advisory_type == "weather":
            processing_stage = "weather"
        elif advisory_type == "livestock":
            processing_stage = "livestock"
        elif advisory_type == "crops":
            processing_stage = "crops"
        elif advisory_type == "mixed":
            processing_stage = "mixed"
        elif early_stage != "default":
            # Use early detection if advisory_type not set yet
            processing_stage = early_stage
        else:
            # Check if we're in assessment phase
            if final_values.get("assessment_summary"):
                processing_stage = "assessment"
            else:
                processing_stage = "default"

    if final_state.next:
        # We hit an interrupt! Send the UI schema
        print(f"[API] Interrupt detected - need user input")
        if final_state.tasks and final_state.tasks[0].interrupts:
            ui_value = final_state.tasks[0].interrupts[0].value

            # Save the AI question to chat history (Firestore - long-term)
            latency_ms = int((time.time() - turn_start) * 1000)
            question_text = ui_value.get("question", "") if isinstance(ui_value, dict) else str(ui_value)
            chat_history.save_message(
                user_id=request.user_id,
                thread_id=request.thread_id,
                role="assistant",
                content=question_text,
                metadata={
                    "type": "quiz",
                    "options": ui_value.get("options", []) if isinstance(ui_value, dict) else [],
                    "latency_ms": latency_ms,
                },
            )
            
            # Add to message buffer (Redis - fast short-term context)
            push_message(
                thread_id=request.thread_id,
                message={
                    "role": "assistant",
                    "content": question_text,
                    "metadata": {
                        "type": "quiz",
                        "options": ui_value.get("options", []) if isinstance(ui_value, dict) else [],
                    },
                },
            )

            return {
                "status": "requires_input",
                "ui": ui_value,
                "processing_stage": processing_stage
            }
        else:
            print(f"[API] Warning: Next nodes exist but no interrupt found")
            return {
                "status": "error",
                "message": "Graph in unexpected state - next nodes but no interrupt",
                "processing_stage": processing_stage
            }

    # Get diagnosis/advice from final state
    diagnosis = final_values.get("diagnosis", "")
    recommendations = final_values.get("recommendations", [])
    assessment_summary = final_values.get("assessment_summary", "")
    advisory_type = final_values.get("advisory_type", "unknown")

    print(f"[API] Final values:")
    print(f"  - assessment_summary: {assessment_summary[:100] if assessment_summary else 'None'}...")
    print(f"  - advisory_type: {advisory_type}")
    print(f"  - diagnosis: {diagnosis[:100] if diagnosis else 'None'}...")
    print(f"  - diagnosis length: {len(diagnosis) if diagnosis else 0}")
    print(f"  - diagnosis type: {type(diagnosis)}")
    print(f"  - recommendations count: {len(recommendations)}")
    print(f"  - processing_stage: {processing_stage}")
    print(f"  - All final_values keys: {list(final_values.keys())}")
    
    # Debug: Check if diagnosis is empty string vs None
    if not diagnosis or (isinstance(diagnosis, str) and not diagnosis.strip()):
        print(f"[API] WARNING: Diagnosis is empty or None!")
        print(f"[API] Advisory type: {advisory_type}")
        print(f"[API] Current issues: {final_values.get('current_issues', [])}")
        print(f"[API] Location: {final_values.get('location', 'Not set')}")
        
        # For weather queries, provide a fallback message
        if advisory_type == "weather":
            diagnosis = "I'm processing your weather request. Please make sure you've provided a location (e.g., 'Hayward, California')."
            print(f"[API] Using fallback weather message")

    # Save the assistant's final response to chat history (Firestore - long-term)
    latency_ms = int((time.time() - turn_start) * 1000)
    chat_history.save_message(
        user_id=request.user_id,
        thread_id=request.thread_id,
        role="assistant",
        content=diagnosis if diagnosis else "No diagnosis generated",
        metadata={
            "advisory_type": advisory_type,
            "recommendations": recommendations,
            "latency_ms": latency_ms,
        },
    )

    # Add to message buffer (Redis - fast short-term context)
    push_message(
        thread_id=request.thread_id,
        message={
            "role": "assistant",
            "content": diagnosis if diagnosis else "No diagnosis generated",
            "metadata": {"advisory_type": advisory_type, "recommendations": recommendations},
        },
    )

    # Persist farm context and mark complete
    farm_context = {
        "location": final_values.get("location"),
        "crops": final_values.get("crops"),
        "farm_size": final_values.get("farm_size"),
        "assessment_summary": assessment_summary,
    }

    chat_history.mark_complete(
        user_id=request.user_id,
        thread_id=request.thread_id,
        advisory_type=advisory_type,
        farm_context={k: v for k, v in farm_context.items() if v},
    )

    # Response format unchanged for backward compatibility
    print(f"[API] Conversation complete for thread {request.thread_id}")
    return {
        "status": "complete",
        "diagnosis": diagnosis if diagnosis else "No diagnosis generated",
        "recommendations": recommendations if recommendations else [],
        "advisory_type": advisory_type,
        "assessment_summary": assessment_summary,
        "processing_stage": processing_stage
    }

# ============================================================================
# THREAD MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/threads")
async def list_threads(
    user_id: str = "anonymous",
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
):
    """List all chat threads for a user with cursor-based pagination."""
    threads, next_cursor = chat_history.get_threads(user_id, limit=limit, cursor=cursor)
    return {"threads": threads, "next_cursor": next_cursor}


@app.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    user_id: str = "anonymous",
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
):
    """Get messages for a specific thread with cursor-based pagination."""
    messages, next_cursor = chat_history.get_messages(
        user_id, thread_id, limit=limit, cursor=cursor
    )
    if not messages and cursor is None:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"thread_id": thread_id, "messages": messages, "next_cursor": next_cursor}


@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, user_id: str = "anonymous"):
    """Delete a chat thread."""
    success = chat_history.delete_thread(user_id, thread_id)
    if not success:
        return JSONResponse(status_code=404, content={"error": "Thread not found"})
    return {"status": "deleted", "thread_id": thread_id}

# ============================================================================
# ANALYTICS ENDPOINT
# ============================================================================

@app.get("/analytics")
async def get_analytics(user_id: str = "anonymous"):
    """Aggregate analytics for a user's chat sessions."""
    data = chat_history.get_analytics(user_id)
    if not data:
        return {"status": "no_data", "message": "No analytics data available."}
    return data

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"[API] Starting Farm Advisory API on port {port}")
    print(f"[API] Features: User-driven assessment + Hybrid routing + Livestock RAG + Chat persistence")
    uvicorn.run(app, host="0.0.0.0", port=port)
