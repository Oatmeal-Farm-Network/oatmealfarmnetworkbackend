"""
Saige history store.

Persists pest diagnoses, soil assessments, and price forecasts per user
so we can show trends on the dashboard and power "your last 3 alerts"
cards. JSON-backed for zero-migration deployment; swap to a SQL table
by replacing `_load` / `_save` / `_file_for`.

Each entry is an append-only record with a type, timestamp, user_id,
and the raw feature output.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

STORE_DIR = Path(os.getenv("HISTORY_STORE_DIR", "./saige_history"))
_lock = threading.Lock()

# Cap how many rows we keep per (user, type) bucket. Anything older is
# dropped — this store is for UX trend cards, not an audit log.
MAX_PER_USER_TYPE = 100

# Strip big blobs from records we persist (don't want to keep base64
# images forever).
def _strip_heavy(record: Dict) -> Dict:
    clean = dict(record)
    clean.pop("image_base64", None)
    clean.pop("raw", None)
    return clean


def _file_for(user_id: str) -> Path:
    safe = "".join(c for c in str(user_id) if c.isalnum() or c in "-_") or "anon"
    return STORE_DIR / f"{safe}.json"


def _load(user_id: str) -> Dict[str, List[Dict]]:
    path = _file_for(user_id)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[history] read error for {user_id}: {e}")
        return {}


def _save(user_id: str, data: Dict[str, List[Dict]]) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    path = _file_for(user_id)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def record(user_id: str, entry_type: str, payload: Dict[str, Any]) -> Dict:
    """Append a record. Returns the saved record (with id + timestamp)."""
    if not user_id:
        user_id = "anon"
    entry = {
        "id": uuid.uuid4().hex,
        "type": entry_type,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "payload": _strip_heavy(payload or {}),
    }
    with _lock:
        data = _load(user_id)
        bucket = data.setdefault(entry_type, [])
        bucket.insert(0, entry)
        if len(bucket) > MAX_PER_USER_TYPE:
            del bucket[MAX_PER_USER_TYPE:]
        _save(user_id, data)
    return entry


def list_for_user(user_id: str, entry_type: Optional[str] = None,
                  limit: int = 20) -> List[Dict]:
    with _lock:
        data = _load(user_id or "anon")
    if entry_type:
        return (data.get(entry_type, []) or [])[:limit]
    merged: List[Dict] = []
    for rows in data.values():
        merged.extend(rows)
    merged.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return merged[:limit]


def delete_entry(user_id: str, entry_id: str) -> bool:
    with _lock:
        data = _load(user_id or "anon")
        hit = False
        for t, rows in data.items():
            before = len(rows)
            data[t] = [r for r in rows if r.get("id") != entry_id]
            if len(data[t]) != before:
                hit = True
        if hit:
            _save(user_id or "anon", data)
        return hit
