# --- schemas/visualizations.py --- (typed chat visualization catalog, Tier 1)
"""Deterministic visualization specs for Saige chat.

The LLM writes the caption. Tools/mappers emit these specs. Invalid or empty
payloads are dropped (``validate_spec`` returns None) so the spoken answer still
ships without a broken chart.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

TIER1_TYPES = (
    "kpi",
    "line_chart",
    "bar_chart",
    "table",
    "alert_card",
    "timeline",
    "progress",
)

MAP_TYPES = (
    "farm_map",
    "field_map",
)

ALLOWED_TYPES = TIER1_TYPES + MAP_TYPES

VizType = Literal[
    "kpi",
    "line_chart",
    "bar_chart",
    "table",
    "alert_card",
    "timeline",
    "progress",
    "farm_map",
    "field_map",
]


class VizAction(BaseModel):
    """Deep-link shown under a visualization (Precision Ag, field page, etc.)."""

    model_config = ConfigDict(extra="ignore")

    label: str
    href: str


class VisualizationSpec(BaseModel):
    """One in-chat visualization. ``data`` shape depends on ``type`` (see plan §6)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: VizType
    title: str
    source_tool: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    actions: List[VizAction] = Field(default_factory=list)


def _has_series(data: Dict[str, Any]) -> bool:
    series = data.get("series")
    return isinstance(series, list) and len(series) > 0


def _has_rows(data: Dict[str, Any]) -> bool:
    rows = data.get("rows")
    return isinstance(rows, list) and len(rows) > 0


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_field_ids(data: Dict[str, Any]) -> bool:
    raw = data.get("field_ids")
    if not isinstance(raw, list) or not raw:
        return False
    return any(_as_int(x) is not None for x in raw)


def validate_spec(raw: Any) -> Optional[VisualizationSpec]:
    """Parse a spec dict. Return None if the type/data cannot be rendered."""
    if not isinstance(raw, dict):
        return None
    viz_type = raw.get("type")
    if viz_type not in ALLOWED_TYPES:
        return None
    try:
        spec = VisualizationSpec.model_validate(raw)
    except ValidationError:
        return None

    data = spec.data or {}
    if spec.type == "kpi" and data.get("value") is None:
        return None
    if spec.type in ("line_chart", "bar_chart") and not _has_series(data):
        return None
    if spec.type == "table" and not _has_rows(data):
        return None
    if spec.type == "farm_map" and not _has_field_ids(data):
        return None
    if spec.type == "field_map" and _as_int(data.get("field_id")) is None:
        return None
    return spec


def spec_to_dict(spec: VisualizationSpec) -> Dict[str, Any]:
    """JSON-ready dump for /chat, SSE done, and history metadata."""
    return spec.model_dump(mode="json")
