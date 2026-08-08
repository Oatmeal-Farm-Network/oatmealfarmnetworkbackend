# --- graph/graph.py --- (Saige LangGraph: User -> Supervisor -> Specialists -> HITL)
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from config import (
    REDIS_ALLOW_MEMORY_FALLBACK,
    REDIS_AVAILABLE,
    REDIS_ENABLED,
    get_redis_url,
    redis_connection_mode,
)
from graph.nodes import (
    execute_node,
    finalize_skip_hitl_node,
    hitl_gate_node,
    joke_route_node,
    policy_gate_node,
    specialist_dispatch_node,
    supervisor_node,
    synthesizer_node,
    user_agent_node,
)
from graph.routing import route_after_policy, route_after_supervisor
from graph.state import SaigeState

print("[Graph] Building Saige farm graph (supervisor architecture)...")

builder = StateGraph(SaigeState)

builder.add_node("user_agent", user_agent_node)
builder.add_node("supervisor", supervisor_node)
builder.add_node("joke", joke_route_node)
builder.add_node("specialists", specialist_dispatch_node)
builder.add_node("synthesizer", synthesizer_node)
builder.add_node("policy_gate", policy_gate_node)
builder.add_node("hitl_gate", hitl_gate_node)
builder.add_node("execute", execute_node)
builder.add_node("finalize", finalize_skip_hitl_node)

builder.add_edge(START, "user_agent")
builder.add_edge("user_agent", "supervisor")

builder.add_conditional_edges(
    "supervisor",
    route_after_supervisor,
    {"joke": "joke", "specialists": "specialists"},
)

builder.add_edge("joke", END)
builder.add_edge("specialists", "synthesizer")
builder.add_edge("synthesizer", "policy_gate")

builder.add_conditional_edges(
    "policy_gate",
    route_after_policy,
    {"hitl": "hitl_gate", "end_skip_hitl": "finalize"},
)

builder.add_edge("hitl_gate", "execute")
builder.add_edge("execute", END)
builder.add_edge("finalize", END)

if REDIS_ENABLED and REDIS_AVAILABLE:
    try:
        from langgraph.checkpoint.redis import RedisSaver

        redis_url = get_redis_url()
        checkpointer = RedisSaver(redis_url)
        checkpointer.setup()
        print(f"[Graph] [INFO] Redis mode: {redis_connection_mode()}")
        print("[Graph] [OK] Using Redis checkpointing")
    except Exception as e:
        if REDIS_ALLOW_MEMORY_FALLBACK:
            print(f"[Graph] [WARN] Redis checkpointing failed: {e}, using MemorySaver")
            checkpointer = MemorySaver()
        else:
            raise RuntimeError(
                f"Redis checkpointing required but failed ({e}). "
                "Start Redis (docker compose up -d redis) or set REDIS_ALLOW_MEMORY_FALLBACK=true."
            ) from e
elif REDIS_ENABLED and not REDIS_AVAILABLE:
    if REDIS_ALLOW_MEMORY_FALLBACK:
        checkpointer = MemorySaver()
        print("[Graph] [WARN] redis package missing — MemorySaver fallback")
    else:
        raise RuntimeError("REDIS_ENABLED=true but redis package is not installed")
else:
    checkpointer = MemorySaver()
    print("[Graph] Using MemorySaver (Redis disabled)")

graph = builder.compile(checkpointer=checkpointer)

__all__ = ["graph", "builder"]

print("=" * 60)
print("Saige Graph Compiled")
print("  User Agent -> Supervisor -> Specialists|Joke -> Synthesizer")
print("  -> Policy Gate -> HITL (if proposals) -> Execute")
print("=" * 60)
