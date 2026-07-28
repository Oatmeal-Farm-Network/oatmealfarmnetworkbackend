# --- core/tool_policies.py --- (Read vs write tool policy for specialist ReAct)
"""Specialists may only call read/analyze tools. Writes go through HITL → Execute."""
from __future__ import annotations

from typing import Any, Iterable, List, Sequence

# Prefixes that imply mutation. Tools matching these are stripped from specialist binds.
_WRITE_PREFIXES = (
    "update_",
    "create_",
    "add_",
    "delete_",
    "remove_",
    "confirm_",
    "reject_",
    "ship_",
    "log_",
    "save_",
    "set_",
    "toggle_",
    "insert_",
    "upsert_",
    "post_",
    "send_",
    "subscribe_",
    "unsubscribe_",
    "approve_",
    "cancel_",
)

# Explicit denylist (covers awkward names)
_WRITE_EXACT = {
    "tell_joke_tool",  # joke has dedicated graph short-circuit; keep ReAct clean
}

# Allowed exception prefixes that look like writes but are reads
_READ_ALLOW_PREFIXES = (
    "get_",
    "list_",
    "count_",
    "search_",
    "find_",
    "fetch_",
    "check_",
    "calculate_",
    "compute_",
    "parse_",
    "detect_",
    "classify_",
    "recommend_",
    "forecast_",
    "geocode_",
    "lookup_",
    "describe_",
    "summarize_",
    "analyze_",
    "query_",
)


def is_write_tool(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if n in _WRITE_EXACT:
        return True
    lower = n.lower()
    for allow in _READ_ALLOW_PREFIXES:
        if lower.startswith(allow):
            return False
    for prefix in _WRITE_PREFIXES:
        if lower.startswith(prefix):
            return True
    # Draft / mutate heuristics
    if "draft" in lower or "mutate" in lower or "write" in lower:
        return True
    return False


def filter_read_only_tools(tools: Sequence[Any]) -> List[Any]:
    kept: List[Any] = []
    for t in tools or []:
        name = getattr(t, "name", None) or getattr(t, "__name__", "") or ""
        if is_write_tool(str(name)):
            continue
        kept.append(t)
    return kept


def write_tool_refusal(tool_name: str) -> str:
    return (
        f"Write tool '{tool_name}' is blocked in specialists. "
        "Describe the change so Saige can create a HITL proposal for approval."
    )


def registry_tool_alias(tool_name: str) -> str:
    """Map LangChain tool name → execute_registry key when possible."""
    n = (tool_name or "").strip()
    if n.endswith("_tool"):
        n = n[: -len("_tool")]
    return n


# Compat alias used by older call sites / docs
filter_tools = filter_read_only_tools
