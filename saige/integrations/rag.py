# --- integrations/rag.py --- (Advanced hybrid RAG on Firestore Vector Search)
"""Dense + lexical retrieval with RRF fusion, optional rerank, Redis cache, citations."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from config import (
    BAKASURA_DOCS_COLLECTION,
    EMBEDDING_MODEL,
    FIRESTORE_DATABASE,
    GCP_CREDENTIALS,
    GCP_LOCATION,
    GCP_PROJECT,
    HITL_CHARLIE_COLLECTION,
    LIVESTOCK_KNOWLEDGE_COLLECTION,
    NEWS_ARTICLES_COLLECTION,
    PLANT_KNOWLEDGE_COLLECTION,
    RAG_AVAILABLE,
    RAG_CACHE_ENABLED,
    RAG_CACHE_TTL_SECONDS,
    RAG_DENSE_CANDIDATES,
    RAG_HYBRID_ENABLED,
    RAG_LEXICAL_CANDIDATES,
    RAG_LEXICAL_SCAN_LIMIT,
    RAG_MIN_SCORE,
    RAG_RERANK_ENABLED,
    RAG_RERANK_TOP_N,
    RAG_REWRITE_ENABLED,
    TOP_K_RESULTS,
)

logger = logging.getLogger("farm_advisory.rag")

if RAG_AVAILABLE:
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from google.cloud.firestore_v1.vector import Vector
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Process-local TTL cache backing Redis
_MEMORY_CACHE: Dict[str, Tuple[float, Any]] = {}
_MEMORY_CACHE_MAX = 256


def _memory_get(key: str):
    item = _MEMORY_CACHE.get(key)
    if not item:
        return None
    expires, value = item
    if time.time() > expires:
        _MEMORY_CACHE.pop(key, None)
        return None
    return value


def _memory_set(key: str, value: Any, ttl: int = RAG_CACHE_TTL_SECONDS):
    if len(_MEMORY_CACHE) >= _MEMORY_CACHE_MAX:
        for k in list(_MEMORY_CACHE.keys())[: max(1, _MEMORY_CACHE_MAX // 10)]:
            _MEMORY_CACHE.pop(k, None)
    _MEMORY_CACHE[key] = (time.time() + ttl, value)


def _normalize_query(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _cache_key(prefix: str, *parts: str) -> str:
    raw = "|".join([prefix, *parts])
    return "saige:rag:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _cache_get(key: str):
    if not RAG_CACHE_ENABLED:
        return None
    hit = _memory_get(key)
    if hit is not None:
        return hit
    client = _get_redis_text_client()
    if not client:
        return None
    try:
        cached = client.get(key)
        if cached:
            value = json.loads(cached)
            _memory_set(key, value)
            return value
    except Exception:
        return None
    return None


def _cache_set(key: str, value: Any):
    if not RAG_CACHE_ENABLED:
        return
    _memory_set(key, value)
    client = _get_redis_text_client()
    if not client:
        return
    try:
        client.setex(key, RAG_CACHE_TTL_SECONDS, json.dumps(value))
    except Exception:
        pass


def _get_redis_text_client():
    if not RAG_CACHE_ENABLED:
        return None
    try:
        from redis_client import get_redis_manager

        return get_redis_manager().get_client(decode_responses=True)
    except Exception:
        return None


def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    *,
    k: int = 60,
    id_key: str = "chunk_id",
) -> List[Dict[str, Any]]:
    """Fuse multiple ranked hit lists with Reciprocal Rank Fusion."""
    scores: Dict[str, float] = {}
    docs: Dict[str, Dict[str, Any]] = {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            cid = str(hit.get(id_key) or hit.get("doc_id") or hash(hit.get("content", "")))
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in docs:
                docs[cid] = dict(hit)
            docs[cid]["rrf_score"] = scores[cid]
    return sorted(docs.values(), key=lambda h: h.get("rrf_score", 0.0), reverse=True)


def chunk_text(
    text: str,
    *,
    target_chars: int = 2800,
    overlap_chars: int = 280,
) -> List[str]:
    """Recursive character chunking with overlap for ingest."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [text]
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + target_chars, n)
        if end < n:
            # Prefer break on paragraph/sentence
            window = text[start:end]
            br = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("; "))
            if br > target_chars // 3:
                end = start + br + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        next_start = max(end - overlap_chars, start + 1)
        if next_start <= start:
            next_start = end
        start = next_start
    return chunks


class RAGSystem:
    """RAG system using Firestore Vector Search (+ hybrid lexical) for one collection."""

    def __init__(self, collection_name: str, label: str = ""):
        self._collection_name = collection_name
        self._label = label or collection_name
        self._db = None
        self._initialized = False
        self._embeddings = None
        self._last_timings: Dict[str, float] = {}

    def _init_embeddings(self):
        if self._embeddings is None and GCP_PROJECT and RAG_AVAILABLE:
            try:
                self._embeddings = GoogleGenerativeAIEmbeddings(
                    model=EMBEDDING_MODEL,
                    project=GCP_PROJECT,
                    location=GCP_LOCATION,
                )
                print(f"[RAG:{self._label}] Embeddings initialized ({EMBEDDING_MODEL})")
            except Exception as e:
                print(f"[RAG:{self._label}] Embeddings init failed: {e}")

    @property
    def firestore_db(self):
        if self._db is None and GCP_PROJECT and RAG_AVAILABLE:
            credentials = None
            if GCP_CREDENTIALS:
                try:
                    from google.oauth2 import service_account

                    credentials = service_account.Credentials.from_service_account_file(
                        GCP_CREDENTIALS,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                except Exception as e:
                    print(f"[RAG:{self._label}] Credentials load failed: {e}")
            try:
                if credentials:
                    self._db = firestore.Client(
                        project=GCP_PROJECT, database=FIRESTORE_DATABASE, credentials=credentials
                    )
                else:
                    self._db = firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE)
                print(f"[RAG:{self._label}] Connected to Firestore ({FIRESTORE_DATABASE})")
            except Exception as e:
                print(f"[RAG:{self._label}] Firestore connection failed: {e}")
        return self._db

    @property
    def collection(self):
        if self.firestore_db:
            return self.firestore_db.collection(self._collection_name)
        return None

    def _get_embedding(self, text: str) -> List[float]:
        self._init_embeddings()
        norm = _normalize_query(text)
        key = _cache_key("emb", self._collection_name, norm) if norm else ""
        if key:
            cached = _cache_get(key)
            if cached is not None:
                self._last_timings["rag_embed_cache_hit"] = 1.0
                return cached
        if not self._embeddings:
            return []
        t0 = time.perf_counter()
        vec = self._embeddings.embed_query(text)
        self._last_timings["rag_embed_ms"] = (time.perf_counter() - t0) * 1000
        if key and vec:
            _cache_set(key, vec)
        return vec

    def initialize(self):
        if not self._initialized and self.collection:
            try:
                docs = list(self.collection.limit(1).get())
                self._initialized = len(docs) > 0
                if self._initialized:
                    print(f"[RAG:{self._label}] Index ready")
            except Exception as e:
                print(f"[RAG:{self._label}] Init error: {e}")
        return self._initialized

    def _hit_from_doc(self, doc, *, score: Optional[float] = None, source: str = "dense") -> Dict[str, Any]:
        data = doc.to_dict() or {}
        meta = dict(data.get("metadata") or {})
        content = data.get("content") or data.get("text") or ""
        doc_id = meta.get("doc_id") or getattr(doc, "id", None) or ""
        chunk_id = meta.get("chunk_id") or f"{doc_id}:{meta.get('chunk_index', 0)}"
        return {
            "content": content,
            "metadata": meta,
            "doc_id": str(doc_id),
            "chunk_id": str(chunk_id),
            "title": meta.get("title") or data.get("title") or self._label,
            "url": meta.get("source_url") or meta.get("url") or data.get("url") or "",
            "score": score,
            "retrieval_source": source,
            "collection": self._collection_name,
            "quote": (content or "")[:240],
        }

    def _dense_search(self, query: str, n_results: int) -> List[Dict[str, Any]]:
        if not self.collection or not query:
            return []
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return []
        t0 = time.perf_counter()
        vector_query = self.collection.find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_embedding),
            distance_measure=DistanceMeasure.COSINE,
            limit=n_results,
        )
        results = list(vector_query.get())
        self._last_timings["rag_knn_ms"] = (time.perf_counter() - t0) * 1000
        hits = []
        for i, doc in enumerate(results):
            # Cosine distance not always exposed; use rank-based proxy score
            proxy = max(0.0, 1.0 - (i * 0.04))
            hits.append(self._hit_from_doc(doc, score=proxy, source="dense"))
        return hits

    def _lexical_search(self, query: str, n_results: int) -> List[Dict[str, Any]]:
        """Keyword/metadata scan over a bounded sample (exact terms: chem, breed, SKU)."""
        if not self.collection or not query:
            return []
        tokens = [t for t in re.findall(r"[A-Za-z0-9\-]{3,}", query.lower()) if t not in {
            "the", "and", "for", "with", "what", "how", "when", "where", "this", "that",
            "from", "have", "about", "help", "please", "need", "want",
        }]
        if not tokens:
            return []
        try:
            # Bound scan — keep small for latency
            docs = list(self.collection.limit(min(RAG_LEXICAL_SCAN_LIMIT, max(20, n_results * 5))).get())
        except Exception as e:
            logger.warning("[RAG:%s] lexical scan failed: %s", self._label, e)
            return []
        scored: List[Tuple[float, Any]] = []
        for doc in docs:
            data = doc.to_dict() or {}
            blob = " ".join([
                str(data.get("content") or ""),
                str(data.get("title") or ""),
                json.dumps(data.get("metadata") or {}),
            ]).lower()
            hits = sum(1 for t in tokens if t in blob)
            if hits:
                scored.append((float(hits) / len(tokens), doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            self._hit_from_doc(doc, score=score, source="lexical")
            for score, doc in scored[:n_results]
        ]

    def _rerank(self, query: str, hits: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
        if not hits:
            return []
        if not RAG_RERANK_ENABLED or len(hits) <= top_n:
            return hits[:top_n]
        # Lightweight lexical+semantic proxy rerank (no extra model dependency)
        q_tokens = set(re.findall(r"[A-Za-z0-9\-]{3,}", query.lower()))
        ranked = []
        for hit in hits:
            content = (hit.get("content") or "").lower()
            overlap = len(q_tokens & set(re.findall(r"[A-Za-z0-9\-]{3,}", content))) if q_tokens else 0
            base = float(hit.get("rrf_score") or hit.get("score") or 0.0)
            score = base + 0.05 * overlap
            hit = dict(hit)
            hit["score"] = score
            ranked.append(hit)
        ranked.sort(key=lambda h: h.get("score", 0.0), reverse=True)
        filtered = [h for h in ranked if float(h.get("score") or 0.0) >= RAG_MIN_SCORE]
        return (filtered or ranked)[:top_n]

    def _rewrite_query(self, query: str) -> str:
        if not RAG_REWRITE_ENABLED:
            return query
        # Deterministic light expand — avoid LLM round-trip cost by default
        q = (query or "").strip()
        if len(q) < 8:
            return q
        return q

    def retrieve_hybrid(self, query: str, n_results: int = TOP_K_RESULTS) -> List[Dict[str, Any]]:
        """Dense + optional lexical retrieve with RRF fusion."""
        self._last_timings = {}
        if not self._initialized:
            self.initialize()
        if not self.collection or not query:
            return []

        rewritten = self._rewrite_query(query)
        norm = _normalize_query(rewritten)
        cache_k = _cache_key("ret", self._collection_name, norm, str(n_results))
        cached = _cache_get(cache_k)
        if cached is not None:
            self._last_timings["rag_cache_hit"] = 1.0
            logger.info("[RAG:%s] cache_hit n=%s", self._label, len(cached))
            return cached

        dense_n = min(max(n_results, RAG_DENSE_CANDIDATES), 24)
        dense = self._dense_search(rewritten, dense_n)
        lexical: List[Dict[str, Any]] = []
        if RAG_HYBRID_ENABLED:
            lexical = self._lexical_search(rewritten, RAG_LEXICAL_CANDIDATES)

        if dense and lexical:
            fused = reciprocal_rank_fusion([dense, lexical])
        else:
            fused = dense or lexical

        hits = self._rerank(rewritten, fused, max(n_results, RAG_RERANK_TOP_N))[:n_results]
        logger.info(
            "[RAG:%s] retrieve dense=%s lexical=%s out=%s timings=%s",
            self._label, len(dense), len(lexical), len(hits), self._last_timings,
        )
        if hits:
            _cache_set(cache_k, hits)
        return hits

    def search(self, query: str, n_results: int = TOP_K_RESULTS) -> List[Dict[str, Any]]:
        """Backward-compatible search → hybrid retrieve."""
        try:
            return self.retrieve_hybrid(query, n_results=n_results)
        except Exception as e:
            print(f"[RAG:{self._label}] Search error: {e}")
            return []

    def get_context_for_query(self, query: str) -> str:
        results = self.search(query)
        if not results:
            return ""
        context_parts = [f"Relevant {self._label} information from database:\n"]
        for i, result in enumerate(results, 1):
            title = result.get("title") or self._label
            cid = result.get("chunk_id") or result.get("doc_id") or i
            context_parts.append(f"{i}. [{cid}] ({title}) {result.get('content', '')}")
        return "\n".join(context_parts)

    def get_citations_for_query(self, query: str) -> List[Dict[str, Any]]:
        """Document-level citation objects for synthesizer / API responses."""
        return [
            {
                "doc_id": h.get("doc_id"),
                "chunk_id": h.get("chunk_id"),
                "title": h.get("title"),
                "url": h.get("url"),
                "score": h.get("score"),
                "quote": h.get("quote") or (h.get("content") or "")[:180],
                "source": h.get("collection") or self._label,
                "snippet": (h.get("content") or "")[:180],
            }
            for h in self.search(query)
        ]

    @property
    def last_timings(self) -> Dict[str, float]:
        return dict(self._last_timings)


# RAG instances — one per collection
rag_livestock = RAGSystem(LIVESTOCK_KNOWLEDGE_COLLECTION, label="livestock_knowledge")
rag_plant = RAGSystem(PLANT_KNOWLEDGE_COLLECTION, label="plant_knowledge")
rag_bakasura = RAGSystem(BAKASURA_DOCS_COLLECTION, label="bakasura-docs")
rag_news = RAGSystem(NEWS_ARTICLES_COLLECTION, label="news_articles")
rag_hitl_charlie = RAGSystem(HITL_CHARLIE_COLLECTION, label="hitl-charlie")

# Backward-compatible alias
rag = rag_livestock
