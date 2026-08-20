"""Graph compile + smoke."""
from graph import graph


def test_graph_has_supervisor_nodes():
    nodes = set(graph.get_graph().nodes)
    for required in ("user_agent", "supervisor", "specialists", "synthesizer", "policy_gate", "hitl_gate", "execute"):
        assert required in nodes


def test_joke_turn():
    config = {"configurable": {"thread_id": "pytest-joke"}, "recursion_limit": 40}
    payload = {
        "history": ["User: tell me a farm joke"],
        "user_message": "tell me a farm joke",
        "people_id": "0",
        "proposals": [],
        "route": [],
    }
    list(graph.stream(payload, config, stream_mode="values"))
    values = graph.get_state(config).values or {}
    assert values.get("diagnosis") or values.get("joke_text")
    assert values.get("visualizations") in (None, [])
