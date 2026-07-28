# Saige graph package (Commit 1 bridge).
#
# Root ``graph.py`` still owns the compiled LangGraph until a later commit moves
# it to ``graph/graph.py``. This package would otherwise shadow that module and
# break ``from graph import graph``. Load the legacy file explicitly.
from __future__ import annotations

import importlib.util
from pathlib import Path

_legacy_path = Path(__file__).resolve().parent.parent / "graph.py"
_spec = importlib.util.spec_from_file_location("saige_legacy_graph", _legacy_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load legacy graph module from {_legacy_path}")
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

graph = _legacy.graph
builder = _legacy.builder

__all__ = ["graph", "builder"]
