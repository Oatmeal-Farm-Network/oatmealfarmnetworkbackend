# Saige chat package (Commit 1 bridge).
#
# Root ``chat.py`` still owns turn handling until a later commit moves it to
# ``chat/service.py``. This package would otherwise shadow that module and
# break ``from chat import run_chat``. Load the legacy file explicitly.
from __future__ import annotations

import importlib.util
from pathlib import Path

_legacy_path = Path(__file__).resolve().parent.parent / "chat.py"
_spec = importlib.util.spec_from_file_location("saige_legacy_chat", _legacy_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load legacy chat module from {_legacy_path}")
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

run_chat = _legacy.run_chat
resume_hitl = _legacy.resume_hitl
iter_chat_events = _legacy.iter_chat_events

__all__ = ["run_chat", "resume_hitl", "iter_chat_events"]
