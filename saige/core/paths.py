# --- core/paths.py --- (Stable Saige root / runtime data path resolution)
"""
Filesystem anchors for the Saige package.

Python modules live under packages (core/, data/, …) while runtime JSON and
media stay under saige/data/. Always resolve those via these helpers so
``dirname(__file__)`` does not drift after moves.
"""
from __future__ import annotations

from pathlib import Path

# saige/ — parent of core/
SAIGE_ROOT: Path = Path(__file__).resolve().parents[1]

# Runtime JSON fallbacks (proposals/plans/monitoring) and local media live here.
# Must remain stable across Python package moves.
RUNTIME_DATA_DIR: Path = SAIGE_ROOT / "data"

# SQL DDL scripts (supervisor control-plane schema).
SQL_DIR: Path = SAIGE_ROOT / "data" / "sql" / "schema"

# Local media fallback when SAIGE_MEDIA_GCS_BUCKET is unset.
DEFAULT_MEDIA_DIR: Path = RUNTIME_DATA_DIR / "saige_media"


def runtime_json_path(filename: str) -> Path:
    """Path to a JSON file under the stable runtime data directory."""
    return RUNTIME_DATA_DIR / filename


def sql_schema_path(filename: str = "saige_supervisor_schema.sql") -> Path:
    """Path to a SQL DDL file under the stable schema directory."""
    return SQL_DIR / filename


__all__ = [
    "SAIGE_ROOT",
    "RUNTIME_DATA_DIR",
    "SQL_DIR",
    "DEFAULT_MEDIA_DIR",
    "runtime_json_path",
    "sql_schema_path",
]
