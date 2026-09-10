"""SQL Server -> Firestore embedding sync.

Preserves import-time RAG dependency check from the original module.
Run from saige/: python -m scripts.sync_embeddings [--once]
"""
from __future__ import annotations

import sys
from pathlib import Path

SAIGE_ROOT = Path(__file__).resolve().parents[1]
if str(SAIGE_ROOT) not in sys.path:
    sys.path.insert(0, str(SAIGE_ROOT))

from core.config import RAG_AVAILABLE

if not RAG_AVAILABLE:
    print(
        "[Sync] RAG dependencies not available. Install pymssql, "
        "google-cloud-firestore, and langchain-google-vertexai."
    )
    sys.exit(1)

from integrations.embeddings import *  # noqa: F401,F403
from integrations.embeddings import sync_main as main  # noqa: F401

if __name__ == "__main__":
    main()
