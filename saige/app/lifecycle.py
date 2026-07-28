# --- app/lifecycle.py --- (FastAPI startup / shutdown for Saige)
"""Shared Redis pool lifecycle for the Saige FastAPI app."""
from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import IS_PRODUCTION, REDIS_ENABLED
from message_buffer import message_buffer
from redis_client import RedisClientManager, get_redis_manager

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
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        logger.addHandler(handler)
else:
    logging.basicConfig(level=logging.INFO)


def resolve_redis_manager(request=None) -> RedisClientManager:
    """Get shared Redis manager from app state, with singleton fallback."""
    if request is not None:
        app_manager = getattr(request.app.state, "redis_manager", None)
        if app_manager is not None:
            return app_manager
    return get_redis_manager()


def check_redis_health(redis_manager: RedisClientManager) -> tuple[bool, float, dict]:
    """Ping Redis and return health tuple (is_healthy, latency_ms, connection_info)."""
    start = time.perf_counter()
    is_healthy = redis_manager.ping()
    latency_ms = (time.perf_counter() - start) * 1000
    info = redis_manager.connection_info()
    return is_healthy, latency_ms, info


# Backward-compatible private aliases used by app.api health routes
_resolve_redis_manager = resolve_redis_manager
_check_redis_health = check_redis_health


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

        healthy, latency_ms, info = check_redis_health(redis_manager)
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
