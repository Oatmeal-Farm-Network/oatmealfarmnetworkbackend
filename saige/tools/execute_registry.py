# --- tools/execute_registry.py --- (Approved-tool runners for Saige Execute node)
"""Only tools registered here may run after HITL approval."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Tuple

logger = logging.getLogger("farm_advisory.execute")

Executor = Callable[[Dict[str, Any]], Tuple[bool, str]]


def _ok(msg: str) -> Tuple[bool, str]:
    return True, msg


def _fail(msg: str) -> Tuple[bool, str]:
    return False, msg


def exec_update_business_profile(args: Dict[str, Any]) -> Tuple[bool, str]:
    from business_data import update_business_profile_tool

    bid = int(args.get("business_id") or 0)
    phone = args.get("phone") or args.get("business_phone") or args.get("BusinessPhone") or ""
    email = args.get("email") or args.get("business_email") or args.get("BusinessEmail") or ""
    website = args.get("website") or args.get("business_website") or args.get("BusinessWebsite") or ""
    name = args.get("business_name") or args.get("name") or args.get("BusinessName") or ""
    msg = update_business_profile_tool.invoke(
        {
            "business_id": bid,
            "business_name": name,
            "description": args.get("description") or "",
            "slogan": args.get("slogan") or "",
            "phone": phone,
            "email": email,
            "website": website,
        }
    )
    # pymssql rowcount can be 0 on success for some drivers â€” treat "Could not" as soft fail only
    ok = "Could not update" not in str(msg) and "No business context" not in str(msg)
    if "Nothing to update" in str(msg):
        ok = False
    return ok, str(msg)


def exec_update_animal(args: Dict[str, Any]) -> Tuple[bool, str]:
    from business_data import update_animal_tool

    def _num(v, default=-1.0):
        if v is None or v == "":
            return default
        try:
            return float(v)
        except Exception:
            return default

    def _flag(v, default=-1):
        if v is None or v == "":
            return default
        if isinstance(v, bool):
            return 1 if v else 0
        try:
            return int(v)
        except Exception:
            return default

    msg = update_animal_tool.invoke(
        {
            "business_id": int(args.get("business_id") or 0),
            "animal_id": int(args.get("animal_id") or args.get("AnimalID") or 0),
            "price": _num(args.get("price")),
            "stud_price": _num(args.get("stud_price")),
            "for_sale": _flag(args.get("for_sale")),
            "for_stud": _flag(args.get("for_stud")),
            "show_on_website": _flag(args.get("show_on_website")),
            "description": args.get("description") or "",
        }
    )
    return "not found" not in str(msg).lower() and "need an animalid" not in str(msg).lower(), str(msg)


def exec_create_field(args: Dict[str, Any]) -> Tuple[bool, str]:
    from field_ops import create_field, parse_field_create_args

    kwargs = parse_field_create_args(args)
    msg = create_field(**kwargs)
    return "Could not" not in msg and "unavailable" not in msg.lower(), msg


def exec_update_field(args: Dict[str, Any]) -> Tuple[bool, str]:
    from field_ops import update_field

    msg = update_field(
        business_id=int(args.get("business_id") or 0),
        field_id=int(args.get("field_id") or args.get("FieldID") or 0),
        name=args.get("name") or args.get("field_name") or "",
        crop_type=args.get("crop_type") or args.get("crop") or "",
        size_hectares=args.get("size_hectares"),
        size_acres=args.get("size_acres") or args.get("acres"),
        planting_date=args.get("planting_date") or "",
        description=args.get("description") or "",
        latitude=args.get("latitude"),
        longitude=args.get("longitude"),
    )
    return "Could not" not in msg, msg


def exec_toggle_monitoring(args: Dict[str, Any]) -> Tuple[bool, str]:
    from field_ops import toggle_monitoring

    enabled = args.get("enabled")
    if enabled is None:
        enabled = args.get("monitoring_enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.lower() in {"1", "true", "yes", "on", "enable", "enabled"}
    msg = toggle_monitoring(
        business_id=int(args.get("business_id") or 0),
        field_id=int(args.get("field_id") or args.get("FieldID") or 0),
        enabled=bool(enabled),
        interval_days=int(args.get("interval_days") or 7),
    )
    return "Could not" not in msg, msg


def exec_save_plan(args: Dict[str, Any]) -> Tuple[bool, str]:
    from plans_store import save_plan

    plan_id = save_plan(
        business_id=str(args.get("business_id") or ""),
        people_id=str(args.get("people_id") or ""),
        title=args.get("title") or "Weekly farm plan",
        items=args.get("items") or [],
        status=args.get("status") or "approved",
    )
    return True, f"Saved plan {plan_id} with {len(args.get('items') or [])} item(s)."


def exec_add_scout(args: Dict[str, Any]) -> Tuple[bool, str]:
    from precision_ag import add_scout_observation_tool

    msg = add_scout_observation_tool.invoke(
        {
            "field_id": int(args.get("field_id") or 0),
            "people_id": str(args.get("people_id") or ""),
            "category": args.get("category") or "general",
            "notes": args.get("notes") or args.get("observation") or "",
            "severity": args.get("severity") or "medium",
        }
    )
    return True, str(msg)


def exec_log_activity(args: Dict[str, Any]) -> Tuple[bool, str]:
    from precision_ag import log_field_activity_tool

    msg = log_field_activity_tool.invoke(
        {
            "field_id": int(args.get("field_id") or 0),
            "people_id": str(args.get("people_id") or ""),
            "activity_type": args.get("activity_type") or args.get("type") or "other",
            "notes": args.get("notes") or "",
        }
    )
    return True, str(msg)


def exec_draft_bridge(args: Dict[str, Any]) -> Tuple[bool, str]:
    """Bridge legacy SaigeDrafts-style payloads into existing draft tools when present."""
    draft_type = (args.get("draft_type") or args.get("type") or "").lower()
    try:
        if draft_type == "produce_listing":
            from actions import draft_produce_listing_tool

            return True, str(draft_produce_listing_tool.invoke(args))
        if draft_type == "event":
            from actions import draft_event_tool

            return True, str(draft_event_tool.invoke(args))
        if draft_type == "blog_post":
            from actions import draft_blog_post_tool

            return True, str(draft_blog_post_tool.invoke(args))
    except Exception as e:
        return False, f"Draft bridge failed: {e}"
    return False, f"Unsupported draft_type '{draft_type}'"


REGISTRY: Dict[str, Executor] = {
    "update_business_profile": exec_update_business_profile,
    "update_account_profile": exec_update_business_profile,
    "update_animal": exec_update_animal,
    "create_field": exec_create_field,
    "update_field": exec_update_field,
    "toggle_monitoring": exec_toggle_monitoring,
    "save_plan": exec_save_plan,
    "add_scout_observation": exec_add_scout,
    "log_field_activity": exec_log_activity,
    "create_draft": exec_draft_bridge,
}


def run_approved_tool(tool: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    tool_l = (tool or "").strip().lower()
    fn = REGISTRY.get(tool_l)
    if not fn:
        # Allow create_field alias from LLM
        if tool_l.startswith("create_field"):
            fn = exec_create_field
        elif tool_l.startswith("update_field"):
            fn = exec_update_field
        elif tool_l.startswith("toggle_"):
            fn = exec_toggle_monitoring
        else:
            return False, f"Unknown tool `{tool}` â€” not in Execute allowlist"
    try:
        return fn(args or {})
    except Exception as e:
        logger.exception("[execute] %s failed", tool_l)
        return False, f"Execute failed: {e}"
