# --- graph/state.py --- (Re-export canonical LangGraph state — do not duplicate)
"""Canonical SaigeState / FarmState live in schemas.models.

This module exists so orchestration code can use::

    from graph.state import SaigeState

without forking the TypedDict definitions.
"""
from __future__ import annotations

from schemas.models import (  # noqa: F401
    AccountIntent,
    FarmState,
    ProposalDraft,
    SaigeState,
    SupervisorRouteDecision,
    VALID_ROUTES,
)

__all__ = [
    "AccountIntent",
    "FarmState",
    "ProposalDraft",
    "SaigeState",
    "SupervisorRouteDecision",
    "VALID_ROUTES",
]
