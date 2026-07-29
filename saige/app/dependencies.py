# --- app/dependencies.py --- (FastAPI dependency helpers for Saige)
"""Auth and request helpers. Does not redesign DI — reuses existing JWT dependency."""
from __future__ import annotations

import logging

from config import (
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    REDIS_ENABLED,
    REDIS_RATE_LIMIT_KEY_TEMPLATE,
)
from jwt_auth import get_current_user, get_current_user_optional  # noqa: F401
from message_buffer import message_buffer

logger = logging.getLogger("farm_advisory")


def check_rate_limit(thread_id: str) -> tuple[bool, int]:
    if not RATE_LIMIT_ENABLED or not REDIS_ENABLED:
        return True, 0
    client = message_buffer.client
    if client is None:
        return True, 0
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


# Backward-compatible private alias used by app.api
_check_rate_limit = check_rate_limit

__all__ = [
    "get_current_user",
    "get_current_user_optional",
    "check_rate_limit",
    "_check_rate_limit",
]
