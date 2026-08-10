# --- graph/routing.py --- (Conditional edge helpers for the supervisor farm graph)
"""Routing helpers extracted from nodes to keep graph.graph → graph.nodes acyclic.

Behavior must match the previous inline helpers in nodes.py exactly.
"""
from __future__ import annotations

from graph.state import SaigeState


def route_after_supervisor(state: SaigeState) -> str:
    routes = state.get("route") or []
    if routes == ["joke"] or (len(routes) == 1 and routes[0] == "joke"):
        return "joke"
    return "specialists"


def route_after_policy(state: SaigeState) -> str:
    if state.get("proposals"):
        return "hitl"
    return "end_skip_hitl"


__all__ = ["route_after_supervisor", "route_after_policy"]
