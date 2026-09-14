"""HITL gate + chat interrupt handling tests."""
from __future__ import annotations

import os

# graph/nodes imports llm at module load; keep unit tests runnable without secrets.
os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("REDIS_ALLOW_MEMORY_FALLBACK", "true")

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from chat.service import _extract_interrupt_payload, _finalize_result, _is_interrupt_exception
from graph.nodes import hitl_gate_node


def test_hitl_gate_imports_and_persists_proposals():
    drafts = [
        {
            "tool": "create_field",
            "args": {"name": "Alpha", "acres": 10},
            "summary": "Create field Alpha",
            "risk": "low_write",
            "domain": "precision_ag",
        }
    ]
    created = [
        {
            "proposal_id": "p-1",
            "tool": "create_field",
            "args": drafts[0]["args"],
            "summary": drafts[0]["summary"],
            "status": "pending",
        }
    ]
    with patch("proposals_store.create_proposals", return_value=created) as create_mock, patch(
        "graph.nodes.interrupt", return_value={"decision": "approve"}
    ) as interrupt_mock:
        out = hitl_gate_node(
            {
                "people_id": "5699",
                "business_id": "15627",
                "thread_id": "t-hitl",
                "proposals": drafts,
                "diagnosis": "Ready to create field.",
            }
        )
    create_mock.assert_called_once()
    interrupt_mock.assert_called_once()
    payload = interrupt_mock.call_args[0][0]
    assert payload["type"] == "hitl_proposals"
    assert payload["proposals"][0]["proposal_id"] == "p-1"
    assert out["proposals"][0]["proposal_id"] == "p-1"
    assert out["hitl_decision"]["decision"] == "approve"


def test_hitl_gate_still_interrupts_when_create_fails():
    drafts = [{"tool": "create_field", "args": {"name": "Beta"}, "summary": "Create Beta"}]
    with patch("proposals_store.create_proposals", side_effect=RuntimeError("db down")), patch(
        "graph.nodes.interrupt", return_value={"decision": "reject"}
    ) as interrupt_mock:
        out = hitl_gate_node(
            {
                "people_id": "1",
                "business_id": None,
                "thread_id": "t-fail",
                "proposals": drafts,
                "diagnosis": "x",
            }
        )
    payload = interrupt_mock.call_args[0][0]
    assert payload["proposals"]
    assert payload["proposals"][0]["proposal_id"]
    assert out["proposals"][0]["proposal_id"]


def test_is_interrupt_exception_detects_graph_interrupt():
    class GraphInterrupt(Exception):
        pass

    assert _is_interrupt_exception(GraphInterrupt("paused")) is True
    assert _is_interrupt_exception(ValueError("boom")) is False


def test_extract_interrupt_payload_from_tasks():
    interrupt = SimpleNamespace(value={"type": "hitl_proposals", "proposals": [{"proposal_id": "x"}]})
    task = SimpleNamespace(interrupts=[interrupt])
    state = SimpleNamespace(tasks=[task], values={})
    assert _extract_interrupt_payload(state)["proposals"][0]["proposal_id"] == "x"


def test_finalize_interrupted_status(monkeypatch):
    interrupt = SimpleNamespace(value={"type": "hitl_proposals", "proposals": [{"proposal_id": "z"}]})
    task = SimpleNamespace(interrupts=[interrupt])
    fake_state = SimpleNamespace(
        next=("hitl_gate",),
        tasks=[task],
        values={"diagnosis": "Please approve.", "proposals": [{"proposal_id": "z"}], "recommendations": []},
    )
    monkeypatch.setattr("chat.service._get_state", lambda *_a, **_k: fake_state)
    monkeypatch.setattr("chat.service.graph", MagicMock())
    result = _finalize_result(
        thread_id="t1",
        people_id="1",
        business_id=None,
        skip_history=True,
        turn_start=0,
        trace_id="tr",
        product="ofn",
    )
    assert result["status"] == "interrupted"
    assert result["proposals"][0]["proposal_id"] == "z"
    assert result["visualizations"] == []
