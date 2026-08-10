#!/usr/bin/env python3
"""Saige RAG eval harness — recall@k, citation presence, latency.

Usage (from saige/):
  python -m scripts.eval_rag
  python scripts/eval_rag.py --limit 10

Does not require a live chat turn for retrieval metrics; uses RAGSystem.search.
Chat latency checks hit /chat when --chat-url is provided.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

SAIGE_ROOT = Path(__file__).resolve().parents[1]
if str(SAIGE_ROOT) not in sys.path:
    sys.path.insert(0, str(SAIGE_ROOT))

GOLDEN = [
    {
        "id": "crop_soil_ph",
        "query": "How do I raise soil pH for tomatoes?",
        "domain": "crop",
        "expect_collection": "plant_knowledge",
        "keywords": ["ph", "soil", "tomato", "lime"],
    },
    {
        "id": "livestock_cattle",
        "query": "What are signs of bloat in cattle?",
        "domain": "livestock",
        "expect_collection": "livestock_knowledge",
        "keywords": ["bloat", "cattle", "rumen"],
    },
    {
        "id": "weather_frost",
        "query": "How do I protect crops from frost tonight?",
        "domain": "weather",
        "expect_collection": None,
        "keywords": ["frost", "protect", "cover"],
    },
    {
        "id": "ofn_docs",
        "query": "How does Saige work on Oatmeal Farm Network?",
        "domain": "bakasura",
        "expect_collection": "bakasura-docs",
        "keywords": ["saige", "oatmeal", "farm"],
    },
    {
        "id": "news_market",
        "query": "What are recent commodity market headlines for corn?",
        "domain": "news",
        "expect_collection": "news_articles",
        "keywords": ["corn", "market", "price"],
    },
]


def _keyword_hit(text: str, keywords: list[str]) -> float:
    t = (text or "").lower()
    if not keywords:
        return 0.0
    hits = sum(1 for k in keywords if k.lower() in t)
    return hits / len(keywords)


def eval_retrieval(limit: int | None = None) -> dict:
    from rag import rag_bakasura, rag_livestock, rag_news, rag_plant

    mapping = {
        "crop": rag_plant,
        "livestock": rag_livestock,
        "bakasura": rag_bakasura,
        "news": rag_news,
    }
    cases = GOLDEN[: limit or len(GOLDEN)]
    rows = []
    for case in cases:
        rag = mapping.get(case["domain"])
        if rag is None:
            rows.append({**case, "skipped": True, "reason": "no rag system"})
            continue
        t0 = time.perf_counter()
        hits = rag.search(case["query"], n_results=5)
        ms = (time.perf_counter() - t0) * 1000
        blob = " ".join(h.get("content") or "" for h in hits)
        kw = _keyword_hit(blob, case.get("keywords") or [])
        has_cite_meta = any(h.get("doc_id") or h.get("chunk_id") for h in hits)
        rows.append({
            "id": case["id"],
            "n_hits": len(hits),
            "keyword_recall": round(kw, 3),
            "citation_meta": has_cite_meta,
            "latency_ms": round(ms, 1),
            "timings": getattr(rag, "last_timings", {}),
        })
    recalls = [r["keyword_recall"] for r in rows if "keyword_recall" in r]
    lats = [r["latency_ms"] for r in rows if "latency_ms" in r]
    return {
        "cases": rows,
        "summary": {
            "n": len(rows),
            "avg_keyword_recall": round(statistics.mean(recalls), 3) if recalls else 0,
            "p50_latency_ms": round(statistics.median(lats), 1) if lats else 0,
            "p95_latency_ms": round(sorted(lats)[max(0, int(len(lats) * 0.95) - 1)], 1) if lats else 0,
            "citation_meta_rate": round(
                sum(1 for r in rows if r.get("citation_meta")) / max(1, len(rows)), 3
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Saige RAG eval harness")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()
    report = eval_retrieval(limit=args.limit)
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
