# --- rag.py --- (RAG system using Firestore Vector Search)
from typing import List, Dict, Any, Optional
from config import (
    GCP_PROJECT, GCP_LOCATION, GCP_CREDENTIALS,
    EMBEDDING_MODEL, TOP_K_RESULTS,
    FIRESTORE_DATABASE, FIRESTORE_COLLECTION,
    RAG_AVAILABLE
)

if RAG_AVAILABLE:
    from google.cloud import firestore
    from google.cloud.firestore_v1.vector import Vector
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from langchain_google_vertexai import VertexAIEmbeddings


class RAGSystem:
    """RAG system using Firestore Vector Search for livestock knowledge."""

    def __init__(self):
        self._db = None
        self._initialized = False
        self._embeddings = None

    def _init_embeddings(self):
        """Initialize embeddings model."""
        if self._embeddings is None and GCP_PROJECT and RAG_AVAILABLE:
            try:
                self._embeddings = VertexAIEmbeddings(
                    model_name=EMBEDDING_MODEL,
                    project=GCP_PROJECT,
                    location=GCP_LOCATION
                )
                print(f"[RAG] Embeddings initialized ({EMBEDDING_MODEL})")
            except Exception as e:
                print(f"[RAG] Embeddings init failed: {e}")

    @property
    def firestore_db(self):
        """Lazy initialization of Firestore client."""
        if self._db is None and GCP_PROJECT and RAG_AVAILABLE:
            credentials = None
            if GCP_CREDENTIALS:
                try:
                    from google.oauth2 import service_account
                    credentials = service_account.Credentials.from_service_account_file(
                        GCP_CREDENTIALS,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                except Exception as e:
                    print(f"[RAG] Credentials load failed: {e}")
            try:
                if credentials:
                    self._db = firestore.Client(
                        project=GCP_PROJECT, database=FIRESTORE_DATABASE, credentials=credentials
                    )
                else:
                    self._db = firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE)
                print(f"[RAG] Connected to Firestore ({FIRESTORE_DATABASE})")
            except Exception as e:
                print(f"[RAG] Firestore connection failed: {e}")
        return self._db

    @property
    def collection(self):
        """Get the Firestore collection."""
        if self.firestore_db:
            return self.firestore_db.collection(FIRESTORE_COLLECTION)
        return None

    def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        self._init_embeddings()
        if self._embeddings:
            return self._embeddings.embed_query(text)
        return []

    def initialize(self):
        """Initialize the RAG system."""
        if not self._initialized and self.collection:
            try:
                docs = list(self.collection.limit(1).get())
                self._initialized = len(docs) > 0
                if self._initialized:
                    print(f"[RAG] Index ready")
            except Exception as e:
                print(f"[RAG] Init error: {e}")
        return self._initialized

    def search(self, query: str, n_results: int = TOP_K_RESULTS) -> List[Dict[str, Any]]:
        """Search for relevant livestock documents."""
        if not self._initialized:
            self.initialize()
        if not self.collection or not query:
            return []
        try:
            query_embedding = self._get_embedding(query)
            if not query_embedding:
                return []
            vector_query = self.collection.find_nearest(
                vector_field="embedding",
                query_vector=Vector(query_embedding),
                distance_measure=DistanceMeasure.COSINE,
                limit=n_results
            )
            results = vector_query.get()
            return [{"content": doc.to_dict().get("content", ""),
                    "metadata": doc.to_dict().get("metadata", {})}
                   for doc in results]
        except Exception as e:
            print(f"[RAG] Search error: {e}")
            return []

    def get_context_for_query(self, query: str) -> str:
        """Get formatted context string for LLM."""
        results = self.search(query)
        if not results:
            return ""
        context_parts = ["Relevant livestock information from database:\n"]
        for i, result in enumerate(results, 1):
            context_parts.append(f"{i}. {result['content']}")
        return "\n".join(context_parts)


rag = RAGSystem()
