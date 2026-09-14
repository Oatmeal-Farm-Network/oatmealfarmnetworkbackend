"""One-shot Firestore embedding backfill.

Run from saige/: python -m scripts.backfill_embeddings [collections...] [--force]
"""
from __future__ import annotations

import sys
from pathlib import Path

SAIGE_ROOT = Path(__file__).resolve().parents[1]
if str(SAIGE_ROOT) not in sys.path:
    sys.path.insert(0, str(SAIGE_ROOT))

from integrations.embeddings import *  # noqa: F401,F403
from integrations.embeddings import backfill_main as main  # noqa: F401

if __name__ == "__main__":
    main(sys.argv[1:])
