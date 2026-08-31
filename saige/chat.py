# Compatibility note for the Saige migration.
#
# IMPORTANT: Python prefers the ``chat/`` package over this file when both exist.
# Active re-exports for ``from chat import run_chat`` live in ``chat/__init__.py``.
#
# Prefer:
#   from chat import run_chat, resume_hitl, iter_chat_events
from chat.service import resume_hitl, run_chat  # noqa: F401
from chat.streaming import iter_chat_events  # noqa: F401

__all__ = ["run_chat", "resume_hitl", "iter_chat_events"]
