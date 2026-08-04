# --- chat/service.py --- (Saige chat turn handler + HITL resume)
"""
Turn handler for the Saige farm graph.
Response shape stays compatible with the existing frontend (/chat).
SSE streaming lives in chat.streaming.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from langgraph.types import Command

from config import SHORT_TERM_N, normalize_chat_product
from graph import builder, graph
from chat.buffer import get_last_n, push_message
from chat.history import chat_history
from observability import log_event, new_trace_id

logger = logging.getLogger("farm_advisory.chat")


def _scoped_thread_id(product: str, thread_id: str) -> str:
    """Isolate Redis buffers / LangGraph checkpoints per product."""
    return f"{normalize_chat_product(product)}:{thread_id}"

_STAGE_LABELS = {
    "user_agent": "Understanding your account & request…",
    "supervisor": "Routing to specialists…",
    "joke": "Fetching a joke…",
    "specialists": "Consulting farm specialists…",
    "synthesizer": "Composing your answer…",
    "policy_gate": "Checking safety policy…",
    "hitl_gate": "Preparing proposals for your approval…",
    "execute": "Applying approved changes…",
    "finalize": "Finishing up…",
}


def _buffer_to_history(last_n: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for m in last_n or []:
        role = (m.get("role") or "").lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            out.append(f"User: {content}")
        elif role in {"assistant", "ai", "saige"}:
            out.append(f"AI: {content}")
    return out


def _safe_stream(active_graph, input_data, config, stream_mode="values"):
    try:
        for event in active_graph.stream(input_data, config, stream_mode=stream_mode):
            yield event
    except Exception as e:
        err = str(e).lower()
        if "no such index" in err and "checkpoint" in err:
            from langgraph.checkpoint.memory import MemorySaver

            print("[chat] Redis index missing - MemorySaver fallback for this turn")
            temp = builder.compile(checkpointer=MemorySaver())
            for event in temp.stream(input_data, config, stream_mode=stream_mode):
                yield event
        else:
            raise


def _empty_state():
    class EmptyState:
        def __init__(self):
            self.next = []
            self.values = {}
            self.tasks = None

    return EmptyState()


def _get_state(active_graph, config):
    try:
        return active_graph.get_state(config)
    except Exception as e:
        err = str(e).lower()
        if "no such index" in err or "checkpoint" in err:
            return _empty_state()
        raise


def _prepare_turn(
    *,
    user_input: str,
    thread_id: str,
    people_id: str,
    business_id: Optional[str],
    image_data: Optional[str],
    skip_history: bool,
    product: Optional[str] = "ofn",
) -> Tuple[dict, Any, Optional[str]]:
    """Returns (langgraph_config, stream_input, trace_id)."""
    product = normalize_chat_product(product)
    scoped_id = _scoped_thread_id(product, thread_id)
    trace_id = new_trace_id()
    config = {"configurable": {"thread_id": f"sup:{scoped_id}"}}
    last_n = get_last_n(scoped_id, SHORT_TERM_N)
    short_term_history = _buffer_to_history(last_n)

    if not skip_history:
        try:
            chat_history.save_message(
                user_id=people_id,
                thread_id=thread_id,
                role="user",
                content=user_input,
                business_id=str(business_id) if business_id else None,
                product=product,
            )
        except Exception as e:
            logger.debug("[chat] save user message failed: %s", e)
        push_message(thread_id=scoped_id, message={"role": "user", "content": user_input})

    state = _get_state(graph, config)
    if state.next:
        resume_payload: Any = user_input
        stripped = (user_input or "").strip().lower()
        if stripped in {"approve", "approved", "yes", "y"}:
            resume_payload = {"decision": "approve"}
        elif stripped in {"reject", "rejected", "no", "n"}:
            resume_payload = {"decision": "reject"}
        log_event("hitl_resume", trace_id=trace_id, thread_id=thread_id)
        return config, Command(resume=resume_payload), trace_id

    user_name = None
    long_term_memory: Dict[str, Any] = {}
    org_memory: Dict[str, Any] = {}
    try:
        from user_profile import get_user_name, get_primary_business_id

        user_name = get_user_name(people_id) if people_id else None
        if not business_id and people_id:
            business_id = get_primary_business_id(people_id)
    except Exception:
        pass
    try:
        long_term_memory = (
            chat_history.get_user_memory(
                people_id,
                product=product,
                business_id=str(business_id) if business_id else None,
            )
            if people_id
            else {}
        )
        if business_id:
            org_memory = chat_history.get_org_memory(
                business_id,
                exclude_user_id=people_id,
                product=product,
            )
    except Exception:
        pass

    history = (short_term_history + [f"User: {user_input}"])[-SHORT_TERM_N:]
    payload = {
        "history": history,
        "user_message": user_input,
        "people_id": people_id,
        "business_id": business_id,
        "thread_id": thread_id,
        "product": product,
        "user_name": user_name,
        "long_term_memory": long_term_memory or {},
        "org_memory": org_memory or {},
        "image_data": image_data,
        "proposals": [],
        "route": [],
        "diagnosis": None,
        "recommendations": [],
    }
    log_event(
        "turn_start",
        trace_id=trace_id,
        thread_id=thread_id,
        people_id=people_id,
        business_id=business_id,
        product=product,
    )
    return config, payload, trace_id


def _finalize_result(
    *,
    thread_id: str,
    people_id: str,
    business_id: Optional[str],
    skip_history: bool,
    turn_start: float,
    trace_id: str,
    product: Optional[str] = "ofn",
) -> Dict[str, Any]:
    product = normalize_chat_product(product)
    scoped_id = _scoped_thread_id(product, thread_id)
    final_state = _get_state(graph, {"configurable": {"thread_id": f"sup:{scoped_id}"}})
    final_values = final_state.values if final_state.values else {}

    if final_state.next:
        interrupt_payload = None
        try:
            for t in final_state.tasks or []:
                interrupts = getattr(t, "interrupts", None) or []
                if interrupts:
                    interrupt_payload = getattr(interrupts[0], "value", interrupts[0])
                    break
        except Exception:
            pass
        diagnosis = (final_values.get("diagnosis") or "") + (
            "\n\nI've prepared change proposal(s) for your approval."
            if (final_values.get("proposals") or (isinstance(interrupt_payload, dict) and interrupt_payload.get("proposals")))
            else ""
        )
        proposals_out = final_values.get("proposals") or []
        if isinstance(interrupt_payload, dict) and interrupt_payload.get("proposals"):
            proposals_out = interrupt_payload.get("proposals") or proposals_out
        result = {
            "status": "interrupted",
            "thread_id": thread_id,
            "response": diagnosis.strip() or "Action requires your approval.",
            "diagnosis": diagnosis,
            "recommendations": final_values.get("recommendations") or [],
            "proposals": proposals_out
            or ((interrupt_payload or {}).get("proposals") if isinstance(interrupt_payload, dict) else [])
            or final_values.get("proposals")
            or [],
            "hitl": interrupt_payload,
            "processing_stage": "hitl",
            "advisory_type": final_values.get("advisory_type"),
            "citations": final_values.get("citations") or [],
            "processing_time_ms": int((time.time() - turn_start) * 1000),
            "trace_id": trace_id,
        }
        log_event("turn_interrupted", trace_id=trace_id, ms=result["processing_time_ms"])
        return result

    response_text = final_values.get("diagnosis") or "I'm here - ask me about your farm."
    if not skip_history:
        try:
            chat_history.save_message(
                user_id=people_id,
                thread_id=thread_id,
                role="assistant",
                content=response_text,
                business_id=str(business_id) if business_id else None,
                product=product,
                metadata={"type": "advisory", "advisory_type": final_values.get("advisory_type"), "trace_id": trace_id},
            )
        except Exception as e:
            logger.debug("[chat] save assistant message failed: %s", e)
        push_message(thread_id=scoped_id, message={"role": "assistant", "content": response_text})

    result = {
        "status": "success",
        "thread_id": thread_id,
        "response": response_text,
        "diagnosis": response_text,
        "recommendations": final_values.get("recommendations") or [],
        "proposals": final_values.get("proposals") or [],
        "policy_violations": final_values.get("policy_violations") or [],
        "citations": final_values.get("citations") or [],
        "processing_stage": "complete",
        "advisory_type": final_values.get("advisory_type"),
        "route": final_values.get("route") or [],
        "handoff": final_values.get("handoff") or "none",
        "processing_time_ms": int((time.time() - turn_start) * 1000),
        "trace_id": trace_id,
    }
    log_event(
        "turn_complete",
        trace_id=trace_id,
        ms=result["processing_time_ms"],
        route=result.get("route"),
        advisory_type=result.get("advisory_type"),
    )
    return result


def run_chat(
    *,
    user_input: str,
    thread_id: str,
    people_id: str,
    business_id: Optional[str] = None,
    image_data: Optional[str] = None,
    skip_history: bool = False,
    product: Optional[str] = "ofn",
) -> Dict[str, Any]:
    """Execute one Saige turn; returns a dict shaped for the /chat JSON body."""
    product = normalize_chat_product(product)
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
    try:
        for _ in _safe_stream(graph, stream_input, config, stream_mode="values"):
            pass
    except Exception as stream_err:
        logger.error("[chat] stream error: %s", stream_err, exc_info=True)
        return {
            "status": "error",
            "message": "Saige encountered an error processing your request. Please try again.",
            "trace_id": trace_id,
        }
    return _finalize_result(
        thread_id=thread_id,
        people_id=people_id,
        business_id=business_id,
        skip_history=skip_history,
        turn_start=turn_start,
        trace_id=trace_id,
        product=product,
    )


def resume_hitl(
    *,
    thread_id: str,
    people_id: str,
    decision: str,
    proposal_id: Optional[str] = None,
    edits: Optional[Dict[str, Any]] = None,
    decisions: Optional[List[Dict[str, Any]]] = None,
    product: Optional[str] = "ofn",
    business_id: Optional[str] = None,
) -> Dict[str, Any]:
    """POST /resume helper - Command(resume=...) into the interrupted farm graph."""
    product = normalize_chat_product(product)
    scoped_id = _scoped_thread_id(product, thread_id)
    config = {"configurable": {"thread_id": f"sup:{scoped_id}"}}
    if decisions:
        payload: Dict[str, Any] = {"decisions": decisions}
    else:
        payload = {
            "decision": decision,
            "proposal_id": proposal_id,
            "edits": edits or {},
        }
    print(f"[chat] HITL resume thread={thread_id} product={product} decision={decision}")
    events_list = list(_safe_stream(graph, Command(resume=payload), config))
    final_state = _get_state(graph, config)
    final_values = final_state.values if final_state.values else {}
    response_text = final_values.get("diagnosis") or "Done."
    try:
        chat_history.save_message(
            user_id=people_id,
            thread_id=thread_id,
            role="assistant",
            content=response_text,
            business_id=str(business_id) if business_id else None,
            product=product,
            metadata={"type": "hitl_result"},
        )
    except Exception:
        pass
    push_message(thread_id=scoped_id, message={"role": "assistant", "content": response_text})
    return {
        "status": "success" if not final_state.next else "interrupted",
        "thread_id": thread_id,
        "response": response_text,
        "diagnosis": response_text,
        "proposals": final_values.get("proposals") or [],
        "hitl_decision": final_values.get("hitl_decision"),
        "events_count": len(events_list),
    }
