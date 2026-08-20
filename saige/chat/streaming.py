# --- chat/streaming.py --- (SSE event stream for Saige chat turns)
"""
Yield SSE-ready events while the farm graph runs.
Event shape stays compatible with the existing frontend (/chat/stream).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, Optional

from chat.service import (
    _STAGE_LABELS,
    _finalize_result,
    _get_state,
    _is_interrupt_exception,
    _prepare_turn,
    _safe_stream,
)
from graph import graph

logger = logging.getLogger("farm_advisory.chat")


def iter_chat_events(
    *,
    user_input: str,
    thread_id: str,
    people_id: str,
    business_id: Optional[str] = None,
    image_data: Optional[str] = None,
    skip_history: bool = False,
    product: Optional[str] = "ofn",
) -> Generator[Dict[str, Any], None, None]:
    """Yield SSE-ready events while the graph runs, then a final done payload."""
    turn_start = time.time()
    config, stream_input, trace_id = _prepare_turn(
        user_input=user_input,
        thread_id=thread_id,
        people_id=people_id,
        business_id=business_id,
        image_data=image_data,
        skip_history=skip_history,
        product=product,
    )
    yield {"type": "status", "stage": "start", "message": "Saige thinking…", "trace_id": trace_id}

    last_diag = ""
    try:
        # updates mode → {node_name: partial_state}
        for update in _safe_stream(graph, stream_input, config, stream_mode="updates"):
            if not isinstance(update, dict):
                continue
            for node_name, partial in update.items():
                label = _STAGE_LABELS.get(node_name, f"Running {node_name}…")
                yield {"type": "status", "stage": node_name, "message": label, "trace_id": trace_id}
                if isinstance(partial, dict):
                    if partial.get("route") is not None:
                        yield {
                            "type": "supervisor",
                            "routes": partial.get("route"),
                            "reasoning": partial.get("supervisor_reasoning"),
                            "handoff": partial.get("handoff"),
                            "trace_id": trace_id,
                        }
                    diag = partial.get("diagnosis")
                    if diag and diag != last_diag:
                        # Stream new text as deltas when diagnosis grows
                        if isinstance(diag, str) and diag.startswith(last_diag):
                            delta = diag[len(last_diag) :]
                        else:
                            delta = str(diag)
                        if delta:
                            yield {"type": "token", "content": delta, "trace_id": trace_id}
                        last_diag = str(diag)
                    if partial.get("proposals"):
                        yield {
                            "type": "proposals",
                            "count": len(partial.get("proposals") or []),
                            "trace_id": trace_id,
                        }
    except Exception as stream_err:
        try:
            st = _get_state(graph, config)
            if st.next or _is_interrupt_exception(stream_err):
                logger.info(
                    "[chat] stream recovering interrupted turn after err=%s",
                    type(stream_err).__name__,
                )
                result = _finalize_result(
                    thread_id=thread_id,
                    people_id=people_id,
                    business_id=business_id,
                    skip_history=skip_history,
                    turn_start=turn_start,
                    trace_id=trace_id,
                    product=product,
                )
                if not last_diag and result.get("response"):
                    yield {"type": "token", "content": result["response"], "trace_id": trace_id}
                yield {"type": "done", **result}
                return
        except Exception:
            pass
        logger.error("[chat] stream error: %s", stream_err, exc_info=True)
        yield {
            "type": "done",
            "status": "error",
            "message": "Saige encountered an error processing your request. Please try again.",
            "visualizations": [],
            "trace_id": trace_id,
        }
        return

    result = _finalize_result(
        thread_id=thread_id,
        people_id=people_id,
        business_id=business_id,
        skip_history=skip_history,
        turn_start=turn_start,
        trace_id=trace_id,
        product=product,
    )
    # If no progressive tokens were emitted, send the full response once
    if not last_diag and result.get("response"):
        yield {"type": "token", "content": result["response"], "trace_id": trace_id}
    yield {"type": "done", **result}
