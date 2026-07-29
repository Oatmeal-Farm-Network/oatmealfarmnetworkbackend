# --- core/policies.py --- (Non-LLM hard checks for Saige HITL proposals)
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# Tools that must never run via Saige
BLOCKED_TOOLS = {
    "change_password",
    "reset_password",
    "set_password",
    "update_password",
    "delete_account",
    "wipe_business",
}

# High-risk chemical / veterinary patterns in free-text args
_UNSAFE_SPRAY = re.compile(
    r"\b(\d+(\.\d+)?)\s*(gal|gallon|lbs?|kg|oz|ml)/?\s*(acre|ha|hectare)?\b",
    re.I,
)
_RESTRICTED_CHEM = re.compile(
    r"\b(paraquat|methyl\s*bromide|chlorpyrifos|ddt|cyanide)\b",
    re.I,
)


def classify_risk(tool: str, args: Dict[str, Any], domain: str = "") -> str:
    tool_l = (tool or "").lower()
    domain_l = (domain or "").lower()
    if tool_l in BLOCKED_TOOLS:
        return "blocked"
    if any(k in tool_l for k in ("spray", "pesticide", "herbicide", "fungicide", "chem")):
        return "high_write"
    if any(k in tool_l for k in ("animal", "vet", "vaccine", "antibiotic", "euthan")):
        return "high_write"
    if domain_l in {"chemical", "veterinary"}:
        return "high_write"
    blob = " ".join(str(v) for v in (args or {}).values() if v is not None)
    if _RESTRICTED_CHEM.search(blob):
        return "blocked"
    if "spray" in blob.lower() and _UNSAFE_SPRAY.search(blob):
        return "high_write"
    if any(k in tool_l for k in ("create_", "update_", "delete_", "toggle_", "add_", "ship_", "confirm_")):
        return "low_write"
    return "low_write"


def evaluate_proposal(proposal: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Return (allowed, violations).
    allowed=False means strip/block the proposal.
    """
    violations: List[Dict[str, Any]] = []
    tool = (proposal.get("tool") or "").lower()
    args = dict(proposal.get("args") or {})
    domain = proposal.get("domain") or ""

    if tool in BLOCKED_TOOLS:
        violations.append({"tool": tool, "reason": "blocked_tool", "action": "block"})
        return False, violations

    if any("password" in str(k).lower() for k in args.keys()):
        violations.append({"tool": tool, "reason": "password_forbidden", "action": "block"})
        return False, violations

    for v in args.values():
        if isinstance(v, str) and "password" in v.lower() and len(v) < 64:
            # likely user asking to set password value
            if re.search(r"(password|passwd|pwd)\s*[:=]", v, re.I):
                violations.append({"tool": tool, "reason": "password_in_args", "action": "block"})
                return False, violations

    blob = " ".join(str(x) for x in args.values() if x is not None)
    if _RESTRICTED_CHEM.search(blob):
        violations.append({"tool": tool, "reason": "restricted_chemical", "action": "block"})
        return False, violations

    risk = classify_risk(tool, args, domain)
    proposal["risk"] = risk
    if risk == "blocked":
        violations.append({"tool": tool, "reason": "risk_blocked", "action": "block"})
        return False, violations

    # Organic-only preference (if set on proposal meta)
    prefs = proposal.get("preferences") or {}
    if prefs.get("organic_only") and re.search(r"\b(synthetic|glyphosate|roundup)\b", blob, re.I):
        violations.append({"tool": tool, "reason": "organic_only_preference", "action": "block"})
        return False, violations

    return True, violations


def filter_proposals(proposals: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    kept: List[Dict[str, Any]] = []
    all_violations: List[Dict[str, Any]] = []
    for p in proposals or []:
        ok, viol = evaluate_proposal(dict(p))
        all_violations.extend(viol)
        if ok:
            kept.append(p)
    return kept, all_violations


# Compat alias used by older call sites / docs
check_proposal = evaluate_proposal
