# --- proactive.py --- (Scheduler-ready proactive Saige jobs)
"""
Cloud Scheduler can POST /alerts/proactive/run (wired in api) to trigger digests.
Creates proposal-friendly notification stubs for frost / plan check-ins.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger("farm_advisory.proactive")


def run_proactive_digest(*, business_id: str = "", people_id: str = "") -> Dict[str, Any]:
    """Lightweight always-on check: weather risk note + open plan reminders."""
    events: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    # Plan check-ins
    try:
        from plans_store import list_plans

        plans = list_plans(business_id=business_id or None, limit=5)
        open_items = 0
        for p in plans:
            for it in p.get("items") or []:
                if (it.get("status") or "open") == "open":
                    open_items += 1
        if open_items:
            events.append(
                {
                    "type": "plan_checkin",
                    "at": now,
                    "message": f"You have {open_items} open plan item(s). Open Saige to review.",
                }
            )
    except Exception as e:
        logger.debug("[proactive] plans: %s", e)

    # Monitoring findings
    try:
        from monitoring_store import list_runs

        runs = list_runs(business_id=business_id or None, limit=3)
        if runs:
            events.append(
                {
                    "type": "monitoring_digest",
                    "at": now,
                    "message": f"Latest monitoring run: {(runs[0].get('summary') or '')[:180]}",
                    "run_id": runs[0].get("run_id"),
                }
            )
    except Exception as e:
        logger.debug("[proactive] monitoring: %s", e)

    # Frost / weather nudge (best-effort)
    try:
        events.append(
            {
                "type": "weather_nudge",
                "at": now,
                "message": "Ask Saige for tonight's frost/heat risk if you have outdoor crops or calves.",
            }
        )
    except Exception:
        pass

    return {"status": "ok", "events": events, "count": len(events)}
