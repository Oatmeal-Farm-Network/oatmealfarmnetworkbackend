"""D2: visualizations[] on chat finalize, history metadata, and SSE done."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("REDIS_ALLOW_MEMORY_FALLBACK", "true")

from chat.service import _finalize_result, _visualizations_from_state


def test_visualizations_from_state_defaults_empty():
    assert _visualizations_from_state(None) == []
    assert _visualizations_from_state({}) == []
    assert _visualizations_from_state({"visualizations": "nope"}) == []
    assert _visualizations_from_state({"visualizations": [1, {"id": "v"}]}) == [{"id": "v"}]


def test_finalize_success_includes_empty_visualizations(monkeypatch):
    fake_state = SimpleNamespace(
        next=(),
        tasks=[],
        values={"diagnosis": "Hello from Saige.", "recommendations": []},
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
    assert result["status"] == "success"
    assert result["visualizations"] == []
    assert result["diagnosis"] == "Hello from Saige."


def test_finalize_success_passes_through_specs(monkeypatch):
    spec = {
        "id": "viz_kpi",
        "type": "kpi",
        "title": "Soil moisture",
        "data": {"value": 28, "unit": "%"},
    }
    fake_state = SimpleNamespace(
        next=(),
        tasks=[],
        values={"diagnosis": "North 40 is at 28%.", "visualizations": [spec]},
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
    assert result["visualizations"] == [spec]


def test_finalize_success_saves_visualizations_in_metadata(monkeypatch):
    spec = {"id": "viz_1", "type": "kpi", "title": "Soil moisture", "data": {"value": 28}}
    fake_state = SimpleNamespace(
        next=(),
        tasks=[],
        values={"diagnosis": "ok", "advisory_type": "crops", "visualizations": [spec]},
    )
    saved = {}

    def _save(**kwargs):
        saved.update(kwargs)
        return True

    monkeypatch.setattr("chat.service._get_state", lambda *_a, **_k: fake_state)
    monkeypatch.setattr("chat.service.graph", MagicMock())
    monkeypatch.setattr("chat.service.chat_history.save_message", _save)
    monkeypatch.setattr("chat.service.push_message", lambda **_k: True)
    result = _finalize_result(
        thread_id="t-save",
        people_id="5699",
        business_id="15627",
        skip_history=False,
        turn_start=0,
        trace_id="tr-1",
        product="ofn",
    )
    assert result["visualizations"] == [spec]
    assert saved["role"] == "assistant"
    assert saved["metadata"]["visualizations"] == [spec]
    assert saved["metadata"]["trace_id"] == "tr-1"


def test_finalize_interrupted_includes_visualizations(monkeypatch):
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
    assert result["visualizations"] == []


def test_stream_done_spreads_visualizations(monkeypatch):
    """SSE done is `{"type": "done", **result}` — field must be on finalize result."""
    fake_state = SimpleNamespace(next=(), tasks=[], values={"diagnosis": "ok"})
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
    done = {"type": "done", **result}
    assert done["type"] == "done"
    assert done["visualizations"] == []
