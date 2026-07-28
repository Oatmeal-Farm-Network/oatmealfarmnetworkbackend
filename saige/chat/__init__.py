# Compatibility surface for ``from chat import run_chat``.
#
# Keep this module light: importing ``chat.history`` / ``chat.buffer`` must not
# pull the LangGraph turn handlers. Public chat entrypoints load lazily.
from __future__ import annotations

from typing import Any

__all__ = [
    "run_chat",
    "resume_hitl",
    "iter_chat_events",
]


def __getattr__(name: str) -> Any:
    if name in {"run_chat", "resume_hitl"}:
        from chat.service import resume_hitl as _resume_hitl
        from chat.service import run_chat as _run_chat

        globals()["run_chat"] = _run_chat
        globals()["resume_hitl"] = _resume_hitl
        return _run_chat if name == "run_chat" else _resume_hitl
    if name == "iter_chat_events":
        from chat.streaming import iter_chat_events as _iter_chat_events

        globals()["iter_chat_events"] = _iter_chat_events
        return _iter_chat_events
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
