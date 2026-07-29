# Compatibility shim — implementation lives in integrations.embeddings (backfill)
"""One-shot Firestore embedding backfill.

Run: python backfill_embeddings.py [collections...] [--force]
"""
from __future__ import annotations

import sys

from integrations.embeddings import *  # noqa: F401,F403
from integrations.embeddings import backfill_main as main  # noqa: F401

if __name__ == "__main__":
    main(sys.argv[1:])
