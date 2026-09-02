# --- graph/farm_viz_intents.py --- (pin QA farm questions to the tools that emit charts)
"""High-confidence farm visualization intents.

The supervisor LLM otherwise sends "any field alerts?" and "should I irrigate"
to weather, and "show my animals" to marketplace listings. Pin those turns
to the specialist that owns the tool, then prefetch the tool so a chart exists
even if the model never calls it.
"""
from __future__ import annotations

import re
from typing import List, Optional

_JOKE = ("joke", "funny", "make me laugh")
_IRRIGATE = (
    "irrigat",
    "should i water",
    "when to water",
    "water my field",
    "water deficit",
    "when should i water",
)
_GROWTH = (
    "growth stage",
    "growing degree",
    "gdd",
    "what stage",
    "crop stage",
    "development stage",
    "how mature",
)
_ANIMALS = (
    "show my animals",
    "list my animals",
    "my animals",
    "show my livestock",
    "list my livestock",
    "my livestock",
    "livestock inventory",
)
_MARKETPLACE = ("for sale", "at stud", "marketplace")
_WEATHER = (
    "weather",
    "forecast",
    "frost",
    "rain",
    "temperature",
    "climate",
    "hail",
    "heat wave",
    "heatwave",
)
_BENCHMARK = (
    "farm overview",
    "whole farm",
    "how's the farm",
    "hows the farm",
    "how is the farm",
    "how's my farm",
    "hows my farm",
    "how is my farm",
    "which field is doing",
    "which of my fields",
    "which field needs",
    "doing best",
    "doing worst",
    "needs the most work",
    "needs most attention",
)
_ACTIVITY = (
    "field activity",
    "activity log",
    "what was applied",
    "operation history",
    "field operation",
    "what have we done",
)
_ZONES = (
    "management zone",
    "stress zone",
    "field zone",
    "variable-rate",
    "variable rate",
)
_FARM_MAP = (
    "list my fields",
    "show my fields",
    "farm map",
    "show my farm map",
    "map of my farm",
    "my field list",
)
_PRICE = (
    "price trend",
    "market price",
    "commodity price",
    "corn price",
    "soy price",
    "soybean price",
    "wheat price",
    "cattle price",
    "hog price",
    "pork price",
)


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\bfeilds\b", "fields", t)
    t = re.sub(r"\bfeild\b", "field", t)
    t = re.sub(r"\bfileds\b", "fields", t)
    return t


def farm_viz_intent(text: str) -> Optional[str]:
    """Return a pinned intent name, or None when the supervisor LLM may route."""
    t = _norm(text)
    if not t:
        return None
    if any(k in t for k in _JOKE):
        return "joke"
    words = t.split()
    if len(words) <= 3 and words[0] in ("hello", "hi", "hey"):
        return "hello"

    weatherish = any(k in t for k in _WEATHER)
    if not weatherish and (
        "field alert" in t
        or ("alert" in t and "field" in t)
        or re.search(r"\bany (field )?alerts?\b", t)
    ):
        return "field_alerts"

    if any(k in t for k in _IRRIGATE):
        return "irrigate"

    if any(k in t for k in _BENCHMARK):
        return "farm_benchmark"

    if any(k in t for k in _ZONES) or re.search(r"\bzones?\b", t):
        return "field_zones"

    if any(k in t for k in _ACTIVITY):
        return "field_activity"

    if any(k in t for k in _FARM_MAP):
        return "farm_map"

    if any(k in t for k in _PRICE) or ("price" in t and "trend" in t):
        return "price_trend"

    if "ndvi" in t or "vegetation index" in t or (
        "how has" in t and "field" in t
    ):
        return "ndvi_history"

    if any(k in t for k in _GROWTH):
        return "growth_stage"

    if any(k in t for k in _MARKETPLACE):
        return None
    if any(k in t for k in _ANIMALS):
        return "animals"
    return None


_PINNED_ROUTES = {
    "irrigate": ["crop"],
    "ndvi_history": ["monitoring"],
    "field_alerts": ["monitoring"],
    "field_zones": ["monitoring"],
    "animals": ["livestock"],
    "growth_stage": ["crop"],
    "farm_benchmark": ["crop"],
    "field_activity": ["crop"],
    "farm_map": ["crop"],
    "price_trend": ["crop"],
    "joke": ["joke"],
}


def pinned_routes(text: str) -> Optional[List[str]]:
    """Exclusive supervisor routes for a farm-viz intent, or None."""
    intent = farm_viz_intent(text)
    routes = _PINNED_ROUTES.get(intent or "")
    return list(routes) if routes else None


def prefetch_farm_viz(
    text: str,
    *,
    people_id: str = "",
    business_id: int = 0,
) -> str:
    """Run the tool that emits the chart for this intent. Returns LLM text."""
    intent = farm_viz_intent(text)
    if not intent or intent in ("joke", "hello"):
        return ""
    bid = str(business_id) if business_id else None
    try:
        if intent == "animals":
            from tools.farm.business_data import list_my_animals_detail_tool

            return str(list_my_animals_detail_tool.invoke({
                "business_id": int(business_id or 0),
            }) or "")

        from tools.agriculture.precision_ag import (
            get_farm_benchmark_tool,
            get_field_activity_log_tool,
            get_field_agronomy_tool,
            get_field_alerts_tool,
            get_field_analysis_tool,
            get_field_gdd_tool,
            get_field_history_tool,
            get_field_irrigation_tool,
            get_field_zones_tool,
            get_price_trends_tool,
            list_my_fields_tool,
            resolve_commodity_name,
            resolve_field_by_name,
            set_session_business_id,
        )

        set_session_business_id(bid)
        if intent == "field_alerts":
            return str(get_field_alerts_tool.invoke({
                "field_id": 0,
                "people_id": people_id,
            }) or "")
        if intent == "farm_benchmark":
            return str(get_farm_benchmark_tool.invoke({
                "people_id": people_id,
            }) or "")
        if intent == "farm_map":
            return str(list_my_fields_tool.invoke({
                "people_id": people_id,
                "business_id": bid or "",
            }) or "")
        if intent == "price_trend":
            commodity = resolve_commodity_name(text) or "Corn"
            return str(get_price_trends_tool.invoke({
                "commodity": commodity,
                "days": 30,
                "people_id": people_id,
            }) or "")

        resolved = resolve_field_by_name(text, people_id, bid)
        if not resolved:
            return (
                "No field name in this question matched the farmer's fields. "
                "Ask them to use a name from their field list."
            )
        fid = int(resolved.get("fieldid") or resolved.get("FieldID") or 0)
        if not fid:
            return ""
        args = {"field_id": fid, "people_id": people_id}
        if intent == "irrigate":
            return str(get_field_irrigation_tool.invoke({**args, "days": 30}) or "")
        if intent == "ndvi_history":
            hist = str(get_field_history_tool.invoke({**args, "months": 6}) or "")
            analysis = str(get_field_analysis_tool.invoke({
                **args,
                "business_id": bid or "",
            }) or "")
            return (hist + "\n\n" + analysis).strip()
        if intent == "growth_stage":
            gdd = str(get_field_gdd_tool.invoke({**args, "days": 180}) or "")
            agro = str(get_field_agronomy_tool.invoke(args) or "")
            return (gdd + "\n\n" + agro).strip()
        if intent == "field_activity":
            return str(get_field_activity_log_tool.invoke(args) or "")
        if intent == "field_zones":
            return str(get_field_zones_tool.invoke(args) or "")
    except Exception as exc:
        print(f"[farm_viz_intents] prefetch failed ({intent}): {exc}")
        return ""
    return ""
