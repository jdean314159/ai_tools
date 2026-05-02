from __future__ import annotations
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class DimensionMismatchError(ValueError):
    """Raised when embedder dimension doesn't match existing ChromaDB collection."""
    pass


class ChromaDBStore:
    """Persistent ChromaDB collection wrapper. One collection per project."""

    def __init__(
        self,
        persist_directory: Path,
        collection_name: str,
        embedding_dimension: int,
    ):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError("chromadb not installed: pip install chromadb")

        self.persist_dir = Path(persist_directory)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.dimension = embedding_dimension

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

        # Check for existing collection and validate dimension
        existing = self._get_existing_collection(collection_name)
        if existing is not None:
            stored_dim = existing.metadata.get("dimension")
            if stored_dim is not None and int(stored_dim) != embedding_dimension:
                raise DimensionMismatchError(
                    f"Embedder dimension mismatch for collection '{collection_name}': "
                    f"existing collection uses {stored_dim}-dim vectors, "
                    f"but current embedder produces {embedding_dimension}-dim vectors. "
                    f"Run: engram-lite-migrate <project_dir> to rebuild with new embedder."
                )

        # Use cosine distance (deterministic similarity = 1 - distance).
        # Default L2 makes thresholding harder because magnitudes vary.
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={
                "dimension": embedding_dimension,
                "hnsw:space": "cosine",
            },
        )

    def _get_existing_collection(self, name: str):
        """Return existing collection or None if not found."""
        try:
            return self.client.get_collection(name)
        except Exception:
            return None

    def validate_dimension(self, expected_dim: int) -> bool:
        """Check if collection dimension matches expected. Returns True if match."""
        stored_dim = self.collection.metadata.get("dimension")
        if stored_dim is None:
            return True  # New collection, no mismatch
        return int(stored_dim) == expected_dim

    def add(
        self,
        episode_id: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if len(embedding) != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {len(embedding)}"
            )
        safe_meta = self._sanitize_metadata(metadata or {})
        safe_meta["indexed_at"] = time.time()
        self.collection.add(
            ids=[episode_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[safe_meta],
        )

    def add_batch(
        self,
        episode_ids: List[str],
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ):
        safe = [
            self._sanitize_metadata(m or {})
            for m in (metadatas or [{} for _ in episode_ids])
        ]
        for m in safe:
            m["indexed_at"] = time.time()
        self.collection.add(
            ids=episode_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=safe,
        )

    def query(
        self,
        query_embedding: List[float],
        n: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        count = self.collection.count()
        if count == 0:
            return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}
        kwargs: dict = dict(
            query_embeddings=[query_embedding],
            n_results=min(n, count),
        )
        if where:
            kwargs["where"] = where
        return self.collection.query(**kwargs)

    def delete(self, episode_id: str):
        self.collection.delete(ids=[episode_id])

    def count(self) -> int:
        return self.collection.count()

    def rebuild_from_episodes(
        self,
        episodes: List[Dict[str, Any]],
        embedder,
        batch_size: int = 50,
    ):
        try:
            self.client.delete_collection(self.collection.name)
        except Exception:
            pass
        self.collection = self.client.create_collection(
            name=self.collection.name,
            metadata={
                "dimension": self.dimension,
                "hnsw:space": "cosine",
            },
        )
        for i in range(0, len(episodes), batch_size):
            batch = episodes[i:i + batch_size]
            ids = [ep.get("id") or str(uuid.uuid4()) for ep in batch]
            texts = [ep.get("text", "") for ep in batch]
            metas = [ep.get("metadata", {}) for ep in batch]
            batch_result = embedder.embed_batch(texts)
            self.add_batch(
                episode_ids=ids,
                texts=texts,
                embeddings=batch_result.embeddings,
                metadatas=metas,
            )

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        safe = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                safe[key] = value
            elif isinstance(value, (list, dict)):
                safe[key] = json.dumps(value)
        return safe
