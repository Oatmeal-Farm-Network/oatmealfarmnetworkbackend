# Compatibility surface for ``from graph import graph``.
#
# Keep this module light: importing ``graph.nodes`` (via the root nodes shim)
# must NOT compile the LangGraph. The compiled ``graph`` / ``builder`` objects
# are loaded lazily on first access.
from __future__ import annotations

from typing import Any

from graph.routing import route_after_policy, route_after_supervisor  # noqa: F401
from graph.state import SaigeState  # noqa: F401

__all__ = [
    "graph",
    "builder",
    "SaigeState",
    "route_after_supervisor",
    "route_after_policy",
    "user_agent_node",
    "supervisor_node",
    "joke_route_node",
    "specialist_dispatch_node",
    "synthesizer_node",
    "policy_gate_node",
    "hitl_gate_node",
    "execute_node",
    "finalize_skip_hitl_node",
]

_NODE_EXPORTS = {
    "user_agent_node",
    "supervisor_node",
    "joke_route_node",
    "specialist_dispatch_node",
    "synthesizer_node",
    "policy_gate_node",
    "hitl_gate_node",
    "execute_node",
    "finalize_skip_hitl_node",
}


def __getattr__(name: str) -> Any:
    if name in {"graph", "builder"}:
        from graph.graph import builder as _builder
        from graph.graph import graph as _graph

        # Cache on module for subsequent access
        globals()["graph"] = _graph
        globals()["builder"] = _builder
        return _graph if name == "graph" else _builder
    if name in _NODE_EXPORTS:
        import graph.nodes as _nodes

        value = getattr(_nodes, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
