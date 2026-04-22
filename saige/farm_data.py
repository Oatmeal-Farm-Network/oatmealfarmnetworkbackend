"""
Business-scoped farm-data tools for Saige.

Read-only views over the OFN backend (port 8000) so the LLM can answer
questions about the farmer's OWN animals and marketplace inventory:
  - "What animals do I have for sale?"
  - "How many goats do I have listed?"
  - "What's in my marketplace inventory?"
  - "Is my spring lamb listing still active?"

Every tool is scoped to a single BusinessID. That BusinessID is injected from
graph state by nodes.py — the LLM should NEVER try to guess it.
"""
from __future__ import annotations

import os
from typing import Optional
import requests
from langchain_core.tools import tool


BACKEND_URL = os.getenv("OFN_BACKEND_URL", "http://localhost:8000").rstrip("/")
HTTP_TIMEOUT = 6


def _fmt_money(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(v, digits: int = 0) -> str:
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


@tool
def list_my_animals_tool(business_id: int = 0, studs_only: bool = False, page: int = 1) -> str:
    """List animals that belong to the current business (the farm/ranch the
    user is logged into). By default returns animals marked for sale; pass
    studs_only=True to see only animals offered at stud. Returns name, DOB
    year, breed(s), and price. Use when the user asks "what animals do I
    have", "my ranch's livestock", "what's for sale on my farm", "show my
    studs". business_id is injected from session state — do not guess it."""
    if not business_id or int(business_id) <= 0:
        return ("No business context is set for this chat. Open Saige from one of "
                "your business pages, or tell me which business you mean.")
    try:
        r = requests.get(
            f"{BACKEND_URL}/api/ranches/profile/{int(business_id)}/animals",
            params={"page": max(1, int(page or 1)), "studs_only": bool(studs_only)},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        return f"Could not fetch animals ({e})."
    animals = data.get("animals") or []
    total = data.get("total") or 0
    if not animals:
        scope = "studs" if studs_only else "animals for sale"
        return f"No {scope} found on this business (BusinessID {business_id})."
    lines = [
        f"Animals — BusinessID {business_id} "
        f"({'studs only' if studs_only else 'for sale'}) — showing "
        f"{len(animals)} of {total}:"
    ]
    for a in animals:
        name = a.get("full_name") or f"Animal #{a.get('animal_id')}"
        dob = a.get("dob_year")
        breeds = ", ".join(a.get("breeds") or []) or "breed n/a"
        price = a.get("price")
        parts = [f"#{a.get('animal_id')} {name}", breeds]
        if dob:
            parts.append(f"DOB {dob}")
        if price is not None:
            parts.append(_fmt_money(price))
        lines.append("  • " + " · ".join(parts))
    if total > len(animals):
        lines.append(f"  (Page {data.get('page', 1)} of {data.get('total_pages', '?')} — "
                     f"ask for the next page to see more.)")
    return "\n".join(lines)


@tool
def list_my_listings_tool(business_id: int = 0) -> str:
    """List the current business's marketplace inventory — produce, meat, and
    processed food, all in one view. Returns title, price, quantity available,
    unit, and whether the listing is currently active/visible. Use when the
    user asks "what do I have in the marketplace", "my inventory", "what
    produce am I selling", "is my meat listing active". business_id is
    injected from session state."""
    if not business_id or int(business_id) <= 0:
        return ("No business context is set. Open Saige from one of your business "
                "pages so I know which inventory to check.")
    try:
        r = requests.get(
            f"{BACKEND_URL}/api/marketplace/seller/listings",
            params={"business_id": int(business_id)},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        listings = r.json() or []
    except Exception as e:
        return f"Could not fetch marketplace listings ({e})."
    if not listings:
        return f"No marketplace listings found for BusinessID {business_id}."

    by_type: dict[str, list] = {}
    for item in listings:
        by_type.setdefault(str(item.get("ProductType") or "unknown"), []).append(item)

    lines = [f"Marketplace inventory — BusinessID {business_id} ({len(listings)} listings):"]
    active_count = 0
    for ptype, items in sorted(by_type.items()):
        lines.append(f"\n  {ptype.title()} ({len(items)}):")
        for it in items[:8]:
            title = (it.get("Title") or "").strip() or f"Listing {it.get('ListingID')}"
            price = _fmt_money(it.get("UnitPrice"))
            qty = _fmt_num(it.get("QuantityAvailable"), 1)
            unit = it.get("UnitLabel") or "unit"
            status = "active" if it.get("IsActive") else "hidden"
            if it.get("IsActive"):
                active_count += 1
            tags = []
            if it.get("IsOrganic"):
                tags.append("organic")
            if it.get("IsLocal"):
                tags.append("local")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(
                f"    • {it.get('ListingID')} {title}{tag_str} · "
                f"{price}/{unit} · qty {qty} · {status}"
            )
        if len(items) > 8:
            lines.append(f"    …and {len(items) - 8} more {ptype} listings.")
    lines.append(f"\n({active_count} of {len(listings)} listings are currently visible to buyers.)")
    return "\n".join(lines)


@tool
def count_my_animals_tool(business_id: int = 0) -> str:
    """Return the count of animals on this business broken down by how they're
    published: for-sale, at-stud, or neither. Quick way to answer "how many
    animals do I have on OFN", "how many of my animals are published". Uses
    the same ranches endpoint as list_my_animals_tool. business_id injected
    from state."""
    if not business_id or int(business_id) <= 0:
        return "No business context is set for this chat."
    counts = {}
    for key, studs in [("for_sale", False), ("at_stud", True)]:
        try:
            r = requests.get(
                f"{BACKEND_URL}/api/ranches/profile/{int(business_id)}/animals",
                params={"page": 1, "studs_only": studs},
                timeout=HTTP_TIMEOUT,
            )
            r.raise_for_status()
            counts[key] = int((r.json() or {}).get("total") or 0)
        except Exception:
            counts[key] = None
    fs = counts.get("for_sale")
    st = counts.get("at_stud")
    lines = [f"Animal counts — BusinessID {business_id}:"]
    lines.append(f"  • For sale: {fs if fs is not None else 'n/a'}")
    lines.append(f"  • At stud:  {st if st is not None else 'n/a'}")
    return "\n".join(lines)


farm_data_tools = [
    list_my_animals_tool,
    list_my_listings_tool,
    count_my_animals_tool,
]
