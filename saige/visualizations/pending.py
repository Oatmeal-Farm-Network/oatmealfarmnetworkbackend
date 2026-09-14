# --- visualizations/pending.py --- (per-turn ContextVar bucket for viz specs)
"""Side channel so tools can emit typed visualization specs without changing
their string return type. The mapper (D4) and graph (D5) drain this list.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict, List, Optional

_pending: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar(
    "saige_viz_pending", default=None
)


def viz_reset() -> None:
    """Clear the bucket at the start of a chat turn."""
    _pending.set([])


def viz_emit(spec: Dict[str, Any]) -> None:
    """Append one spec dict. No-op if spec is not a dict."""
    if not isinstance(spec, dict):
        return
    bucket = _pending.get()
    if bucket is None:
        bucket = []
        _pending.set(bucket)
    bucket.append(spec)


def viz_take() -> List[Dict[str, Any]]:
    """Return a copy of pending specs and empty the bucket."""
    out = list(_pending.get() or [])
    _pending.set([])
    return out
