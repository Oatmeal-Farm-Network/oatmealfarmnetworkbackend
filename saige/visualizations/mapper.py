# --- visualizations/mapper.py --- (deterministic pending-spec filter)
"""Turn raw tool emits into JSON-ready visualization specs.

No LLM. Invalid payloads are dropped. Caps and dedupe keep the chat bubble
small enough for SaigePage (3 cards) and the payload bounded.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from schemas.visualizations import spec_to_dict, validate_spec

MAX_SPECS = 3
MAX_SERIES_POINTS = 90
MAX_TABLE_ROWS = 50


def _trim_data(viz_type: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Cap series/rows. Return None if the spec would be empty after trim."""
    out = dict(data or {})
    if viz_type in ("line_chart", "bar_chart"):
        series = out.get("series")
        if not isinstance(series, list) or not series:
            return None
        out["series"] = series[-MAX_SERIES_POINTS:]
    elif viz_type == "table":
        rows = out.get("rows")
        if not isinstance(rows, list) or not rows:
            return None
        out["rows"] = rows[:MAX_TABLE_ROWS]
    return out


def map_pending(raw_list: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
    """Validate, dedupe by (type, title), cap counts. Empty/bad input → []."""
    if not raw_list:
        return []

    seen: set[Tuple[str, str]] = set()
    mapped: List[Dict[str, Any]] = []
    for raw in raw_list:
        spec = validate_spec(raw)
        if spec is None:
            continue
        key = (spec.type, spec.title)
        if key in seen:
            continue
        dumped = spec_to_dict(spec)
        trimmed = _trim_data(spec.type, dumped.get("data") or {})
        if trimmed is None:
            continue
        dumped["data"] = trimmed
        seen.add(key)
        mapped.append(dumped)
        if len(mapped) >= MAX_SPECS:
            break
    return mapped
