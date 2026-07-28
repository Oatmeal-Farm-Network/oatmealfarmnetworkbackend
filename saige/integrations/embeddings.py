# --- integrations/embeddings.py ---
"""Embedding maintenance jobs for Saige RAG.

Contains:
  - SQL Server -> Firestore sync (formerly sync_embeddings.py)
  - Collection embedding backfill (formerly backfill_embeddings.py)

CLI entrypoints remain via root shims:
  python sync_embeddings.py [--once]
  python backfill_embeddings.py [collections...] [--force]
"""
from __future__ import annotations

import sys
import time
import hashlib
import datetime
import os
from typing import Dict, List, Any, Iterable, Optional

from config import (
    ALLOWED_TABLES, FIRESTORE_COLLECTION,
    SYNC_INTERVAL_HOURS, RAG_AVAILABLE,
)

# Sync deps (Vector, database, rag) are imported lazily in sync_* so the
# backfill path does not require SQL Server packages at import time.


# ---------------------------------------------------------------------------
# Helpers (sync)
# ---------------------------------------------------------------------------

def row_to_text(table_name: str, row: Dict[str, Any]) -> str:
    """Convert a SQL row dict to a human-readable text string."""
    parts = [f"Table: {table_name}"]
    for key, value in row.items():
        if value is not None:
            parts.append(f"{key}: {value}")
    return " | ".join(parts)


def content_hash(text: str) -> str:
    """SHA-256 hex digest of the text content (for change detection)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_doc_id(table_name: str, row: Dict[str, Any]) -> str:
    """Deterministic Firestore document ID from table + row content.

    Uses the first column value as the primary key hint. Falls back to
    a hash of the full row if no columns are available.
    """
    first_val = next(iter(row.values()), None) if row else None
    if first_val is not None:
        safe = str(first_val).replace("/", "_")
        return f"{table_name}_{safe}"
    return f"{table_name}_{content_hash(str(row))[:16]}"


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def sync_table(table_name: str) -> Dict[str, int]:
    """Sync all rows from one SQL Server table into Firestore.

    Returns counts: {"synced": N, "skipped": N, "errors": N}
    """
    from google.cloud.firestore_v1.vector import Vector
    from database import db
    from rag import rag

    collection = rag.collection
    if not collection:
        print(f"[Sync] Firestore collection unavailable, skipping {table_name}")
        return {"synced": 0, "skipped": 0, "errors": 0}

    rows = db.fetch_all(table_name)
    if not rows:
        print(f"[Sync] {table_name}: 0 rows found")
        return {"synced": 0, "skipped": 0, "errors": 0}

    synced = 0
    skipped = 0
    errors = 0
    batch = rag.firestore_db.batch()
    batch_count = 0

    for row in rows:
        try:
            text = row_to_text(table_name, row)
            text_hash = content_hash(text)
            doc_id = make_doc_id(table_name, row)
            doc_ref = collection.document(doc_id)

            # Check if document exists with same content hash
            existing = doc_ref.get()
            if existing.exists:
                existing_hash = (existing.to_dict() or {}).get("metadata", {}).get("content_hash")
                if existing_hash == text_hash:
                    skipped += 1
                    continue

            # Generate embedding
            embedding = rag._get_embedding(text)
            if not embedding:
                print(f"[Sync] Failed to generate embedding for {doc_id}")
                errors += 1
                continue

            now = datetime.datetime.utcnow().isoformat()
            batch.set(doc_ref, {
                "embedding": Vector(embedding),
                "content": text,
                "metadata": {
                    "table": table_name,
                    "source": "sql_server",
                    "content_hash": text_hash,
                    "synced_at": now,
                },
                "source_table": table_name,
                "synced_at": now,
            })
            synced += 1
            batch_count += 1

            # Firestore batch limit is 500 writes
            if batch_count >= 500:
                batch.commit()
                batch = rag.firestore_db.batch()
                batch_count = 0

        except Exception as e:
            print(f"[Sync] Error processing row in {table_name}: {e}")
            errors += 1

    # Commit remaining batch
    if batch_count > 0:
        batch.commit()

    return {"synced": synced, "skipped": skipped, "errors": errors}


def sync_all():
    """Sync all allowed tables from SQL Server to Firestore."""
    print(f"\n[Sync] Starting sync at {datetime.datetime.utcnow().isoformat()}")
    print(f"[Sync] Tables: {', '.join(ALLOWED_TABLES)}")

    total = {"synced": 0, "skipped": 0, "errors": 0}

    for table in ALLOWED_TABLES:
        print(f"[Sync] Processing {table}...")
        counts = sync_table(table)
        print(f"[Sync]   {table}: synced={counts['synced']}, "
              f"skipped={counts['skipped']}, errors={counts['errors']}")
        for key in total:
            total[key] += counts[key]

    print(f"[Sync] Done — total synced={total['synced']}, "
          f"skipped={total['skipped']}, errors={total['errors']}")
    return total


def sync_main():
    from database import db
    from rag import rag

    once = "--once" in sys.argv

    # Initialize RAG (ensures Firestore + embeddings are ready)
    rag._init_embeddings()
    if not rag.firestore_db:
        print("[Sync] Cannot connect to Firestore. Check GCP credentials.")
        sys.exit(1)
    if not db.connection:
        print("[Sync] Cannot connect to SQL Server. Check DB_* env vars.")
        sys.exit(1)

    print(f"[Sync] Connected to SQL Server and Firestore")
    print(f"[Sync] Mode: {'one-time' if once else f'polling every {SYNC_INTERVAL_HOURS}h'}")

    if once:
        sync_all()
    else:
        while True:
            sync_all()
            print(f"[Sync] Next sync in {SYNC_INTERVAL_HOURS} hours...")
            time.sleep(SYNC_INTERVAL_HOURS * 3600)


# Alias for sync shim callers that expect ``main``.
main = sync_main


# ============================================================================
# BACKFILL (from backfill_embeddings.py)
# ============================================================================

# Backfill Google / Firestore / embedding clients are constructed lazily in
# make_db / make_embedder / backfill so importing this module stays light.
from dotenv import load_dotenv
load_dotenv()

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
CREDS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
DATABASE = os.getenv("FIRESTORE_DATABASE", "charlie").strip()
EMBED_MODEL = "models/text-embedding-004"
BATCH_SIZE = 100  # Firestore commit batch size (well under 500 limit)
EMBED_RPS_PAUSE = 0.05  # ~20 req/s — safe under default Google quota


# Per-collection text extraction. We don't touch existing fields (chunk_id,
# content_vector, etc.) — just add `embedding`.
def text_for_doc(coll_name: str, data: dict) -> str:
    if coll_name == "news_articles":
        # Title + description + content (strip HTML tags lightly)
        import re
        parts = [str(data.get("title") or ""), str(data.get("description") or "")]
        content = str(data.get("content") or "")
        # Strip HTML tags so embedding is on prose, not markup
        content = re.sub(r"<[^>]+>", " ", content)
        content = re.sub(r"\s+", " ", content)
        parts.append(content)
        text = " ".join(p for p in parts if p).strip()
        return text[:8000]  # text-embedding-004 supports up to 2048 tokens (~8k chars)
    # bakasura-docs and hitl-charlie store chunked PDF text under `content`
    return str(data.get("content") or "")[:8000]


def make_db():
    from google.cloud import firestore
    from google.oauth2 import service_account

    if CREDS_PATH:
        creds = service_account.Credentials.from_service_account_file(
            CREDS_PATH, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return firestore.Client(project=PROJECT, database=DATABASE, credentials=creds)
    return firestore.Client(project=PROJECT, database=DATABASE)


def make_embedder():
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(model=EMBED_MODEL, project=PROJECT)


def backfill(coll_name: str, force: bool = False) -> dict:
    from google.cloud.firestore_v1.vector import Vector

    db = make_db()
    embedder = make_embedder()
    coll = db.collection(coll_name)

    total = coll.count().get()[0][0].value
    print(f"\n[{coll_name}] {total} total docs (force={force})")

    embedded = 0
    skipped = 0
    no_text = 0
    errors = 0
    batch = db.batch()
    batch_count = 0

    for snap in coll.stream():
        data = snap.to_dict() or {}

        # Skip if already has a usable embedding (unless forcing)
        if not force:
            existing = data.get("embedding")
            if existing is not None:
                # Vector type or non-empty list both count
                if hasattr(existing, "to_map_value") or (isinstance(existing, list) and existing):
                    skipped += 1
                    continue

        text = text_for_doc(coll_name, data)
        if not text or len(text) < 5:
            no_text += 1
            continue

        try:
            vec = embedder.embed_query(text)
        except Exception as e:
            print(f"  [{snap.id}] embed error: {e}")
            errors += 1
            time.sleep(0.5)
            continue

        if not vec:
            errors += 1
            continue

        batch.update(snap.reference, {"embedding": Vector(vec)})
        batch_count += 1
        embedded += 1

        if batch_count >= BATCH_SIZE:
            batch.commit()
            batch = db.batch()
            batch_count = 0
            print(f"  ...committed batch (running total embedded={embedded}, skipped={skipped})")
            time.sleep(EMBED_RPS_PAUSE)

    if batch_count > 0:
        batch.commit()

    print(f"[{coll_name}] done: embedded={embedded}, skipped={skipped}, "
          f"no_text={no_text}, errors={errors}")
    return {"embedded": embedded, "skipped": skipped, "no_text": no_text, "errors": errors}


def backfill_main(argv: list[str]):
    force = "--force" in argv
    args = [a for a in argv if not a.startswith("--")]

    targets = args or ["bakasura-docs", "hitl-charlie", "news_articles"]
    summary = {}
    for t in targets:
        try:
            summary[t] = backfill(t, force=force)
        except Exception as e:
            print(f"[{t}] FATAL: {e}")
            summary[t] = {"error": str(e)}

    print("\n=== Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in {"backfill", "sync"}:
        cmd = args.pop(0)
        if cmd == "backfill":
            backfill_main(args)
        else:
            sys.argv = [sys.argv[0], *args]
            sync_main()
    else:
        sync_main()
