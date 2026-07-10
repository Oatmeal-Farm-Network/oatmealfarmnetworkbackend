from __future__ import annotations

from pathlib import Path

import pytest


def pytest_collect_file(file_path: Path, parent: pytest.Collector):
    """Collect custom *_unit.py and *_smoke.py files when pytest scans folders."""
    if file_path.suffix == ".py" and file_path.name.endswith("_unit.py"):
        return pytest.Module.from_parent(parent, path=file_path)
    return None


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list[pytest.Item]):
    """Deduplicate nodeids so custom unit collection does not double-run explicit file invocations."""
    seen: set[str] = set()
    unique_items: list[pytest.Item] = []
    for item in items:
        if item.nodeid in seen:
            continue
        seen.add(item.nodeid)
        unique_items.append(item)
    items[:] = unique_items