"""Helpers for lazy, non-import-time schema/bootstrap work.

Import-time DB I/O is forbidden: it blocks Cloud Run boot when the DB/proxy
is unavailable and breaks read-only staging.
"""
from __future__ import annotations

import os
from typing import Callable


def skip_schema_ensure() -> bool:
    """When true, no runtime DDL/seed should run (RO staging, CI, etc.)."""
    return os.getenv("SKIP_SCHEMA_ENSURE", "").lower() in ("1", "true", "yes")


def run_schema_ensure(label: str, fn: Callable[[], None]) -> None:
    """Run fn once-ish; never raise to the caller."""
    if skip_schema_ensure():
        return
    try:
        fn()
    except Exception as e:
        print(f"[{label}] schema ensure skipped: {e}")
