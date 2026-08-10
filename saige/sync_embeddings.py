# Compatibility shim — implementation lives in integrations.embeddings (sync)
"""SQL Server -> Firestore embedding sync.

Preserves import-time RAG dependency check from the original module.
Run: python sync_embeddings.py [--once]
"""
from __future__ import annotations

import sys

from config import RAG_AVAILABLE

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
