# --- core/logging.py --- (Structured turn / LLM / latency traces)
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("farm_advisory.trace")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


@contextmanager
def trace_span(
    name: str,
    *,
    trace_id: Optional[str] = None,
    **fields: Any,
) -> Iterator[Dict[str, Any]]:
    tid = trace_id or new_trace_id()
    start = time.perf_counter()
    payload: Dict[str, Any] = {"trace_id": tid, "span": name, **fields}
    try:
        yield payload
        payload["ok"] = True
    except Exception as e:
        payload["ok"] = False
        payload["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        payload["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        logger.info("[trace] %s", payload)


def log_event(event: str, *, trace_id: Optional[str] = None, **fields: Any) -> None:
    logger.info("[trace] %s", {"event": event, "trace_id": trace_id, **fields})
