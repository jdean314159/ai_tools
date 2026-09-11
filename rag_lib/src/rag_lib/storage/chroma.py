"""
rag_lib.storage.chroma

ChromaDB storage backend.

D11: Embedding model name and dimensions stored in collection metadata.
     Mismatch raises StorageError with clear migration instructions.
D13: All collections created with hnsw:space=cosine.
D14: Content-addressed chunk IDs prevent duplicate ingestion.
D16: threading.Lock serializes all writes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from .base import StoredChunk
from ..errors import StorageError

logger = logging.getLogger(__name__)


class ChromaStorage:
    """ChromaDB-backed vector store.

    Args:
        path:             Persistent storage directory.
        collection_prefix: Prefix added to all collection names.
        embed_model:      Name of the embedding model used to build vectors.
                          Stored in collection metadata and verified on each retrieve.
        embed_dimensions: Dimension count of the embedding model. Stored at creation.
    """

    def __init__(
        self,
        path: str | Path = "~/.rag_lib/chroma",
        collection_prefix: str = "rag_",
        embed_model: str = "nomic-embed-text-v2-moe",
        embed_dimensions: int | None = None,
    ) -> None:
        self._path = Path(path).expanduser()
        self._path.mkdir(parents=True, exist_ok=True)
        self._prefix = collection_prefix
        self._embed_model = embed_model
        self._embed_dimensions = embed_dimensions
        self._lock = threading.Lock()
        self._client = self._make_client()
        self._collections: dict[str, Any] = {}  # name → chromadb.Collection cache

    # ------------------------------------------------------------------
    # VectorStore Protocol implementation
    # ------------------------------------------------------------------

    def add(
        self,
        chunks: list[Any],  # list[TextChunk]
        embeddings: list[list[float]],
        collection: str = "default",
    ) -> None:
        """Store chunks with embeddings. Upserts on duplicate chunk_id (D14)."""
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise StorageError(
                f"Chunk count ({len(chunks)}) != embedding count ({len(embeddings)})"
            )

        coll = self._get_or_create_collection(collection)

        # Discover dimensions from first embedding if not yet known
        if self._embed_dimensions is None and embeddings:
            self._embed_dimensions = len(embeddings[0])

        ids, docs, metas = [], [], []
        for chunk, emb in zip(chunks, embeddings):
            file_hash = chunk.metadata.get("file_hash", "0" * 16)
            cid = chunk.chunk_id(file_hash) if hasattr(chunk, "chunk_id") else chunk.source_id

            meta = {
                "source_id": chunk.source_id,
                "doc_type": chunk.doc_type,
                "context_text": chunk.context_text[:4096],  # ChromaDB metadata char limit
                "strategy": chunk.metadata.get("strategy", "unknown"),
                "is_table": bool(chunk.metadata.get("is_table", False)),
                "page": int(chunk.metadata.get("page", -1)),
                "section": str(chunk.metadata.get("section", "")),
                "file_hash": file_hash,
            }

            ids.append(cid)
            docs.append(chunk.text)
            metas.append(meta)

        _CHROMA_MAX_BATCH = 5000  # ChromaDB hard limit is ~5461; use 5000 for safety
        with self._lock:
            self._mark_collection_updating(collection)
            for i in range(0, len(ids), _CHROMA_MAX_BATCH):
                coll.upsert(
                    ids=ids[i : i + _CHROMA_MAX_BATCH],
                    documents=docs[i : i + _CHROMA_MAX_BATCH],
                    embeddings=embeddings[i : i + _CHROMA_MAX_BATCH],
                    metadatas=metas[i : i + _CHROMA_MAX_BATCH],
                )

        logger.debug("Stored %d chunks in collection '%s'", len(chunks), collection)

    def search(
        self,
        query_vector: list[float],
        n_results: int = 10,
        collection: str = "default",
    ) -> list[StoredChunk]:
        """Return up to n_results chunks by cosine similarity (D13)."""
        coll = self._get_or_create_collection(collection)
        count = coll.count()
        if count == 0:
            return []

        k = min(n_results, count)
        try:
            results = coll.query(
                query_embeddings=[query_vector],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise StorageError(f"ChromaDB query failed: {exc}") from exc

        chunks: list[StoredChunk] = []
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        ids = (results.get("ids") or [[]])[0]

        for doc, meta, dist, cid in zip(docs, metas, distances, ids):
            # ChromaDB cosine distance ∈ [0, 2]; convert to similarity [0, 1]
            score = max(0.0, 1.0 - float(dist) / 2.0)
            chunks.append(
                StoredChunk(
                    chunk_id=cid,
                    text=doc,
                    context_text=meta.get("context_text", doc),
                    score=round(score, 4),
                    source_id=meta.get("source_id", ""),
                    doc_type=meta.get("doc_type", "unknown"),
                    metadata={
                        k: v
                        for k, v in meta.items()
                        if k not in ("source_id", "doc_type", "context_text")
                    },
                )
            )

        return chunks

    def get_by_ids(
        self,
        chunk_ids: list[str],
        collection: str = "default",
    ) -> list[StoredChunk]:
        """Materialize stored chunks by ID, preserving the requested order."""
        if not chunk_ids:
            return []

        coll = self._get_or_create_collection(collection)
        try:
            results = coll.get(ids=chunk_ids, include=["documents", "metadatas"])
        except Exception as exc:
            raise StorageError(f"ChromaDB ID lookup failed: {exc}") from exc

        chunks_by_id: dict[str, StoredChunk] = {}
        for cid, doc, meta in zip(
            results.get("ids", []),
            results.get("documents", []),
            results.get("metadatas", []),
        ):
            meta = meta or {}
            chunks_by_id[cid] = StoredChunk(
                chunk_id=cid,
                text=doc or "",
                context_text=meta.get("context_text", doc or ""),
                score=0.0,
                source_id=meta.get("source_id", ""),
                doc_type=meta.get("doc_type", "unknown"),
                metadata={
                    key: value
                    for key, value in meta.items()
                    if key not in ("source_id", "doc_type", "context_text")
                },
            )
        return [chunks_by_id[cid] for cid in chunk_ids if cid in chunks_by_id]

    def delete_by_source(
        self,
        file_path: str,
        collection: str = "default",
    ) -> int:
        """Delete all chunks from a specific source file (D14: re-ingest dedup)."""
        coll = self._get_or_create_collection(collection)
        try:
            results = coll.get(
                where={"source_id": {"$regex": f"^{re.escape(file_path)}"}},
                include=["metadatas"],
            )
        except Exception:
            # Fallback: get all and filter
            try:
                results = coll.get(include=["metadatas"])
                ids_to_delete = [
                    cid
                    for cid, meta in zip(
                        results.get("ids", []),
                        results.get("metadatas", []),
                    )
                    if meta.get("source_id", "").startswith(file_path)
                ]
            except Exception as exc:
                logger.warning("delete_by_source failed for '%s': %s", file_path, exc)
                return 0
        else:
            ids_to_delete = results.get("ids", [])

        if ids_to_delete:
            with self._lock:
                self._mark_collection_updating(collection)
                coll.delete(ids=ids_to_delete)
            logger.debug("Deleted %d chunks from '%s'", len(ids_to_delete), file_path)

        return len(ids_to_delete)

    def list_collections(self) -> list[str]:
        """Return collection names without the prefix."""
        prefix = self._prefix
        return [
            c.name[len(prefix) :] if c.name.startswith(prefix) else c.name
            for c in self._client.list_collections()
        ]

    def delete_collection(self, collection: str) -> None:
        full_name = f"{self._prefix}{collection}"
        with self._lock:
            try:
                self._client.delete_collection(full_name)
                self._collections.pop(collection, None)
                self._mutation_marker_path(collection).unlink(missing_ok=True)
                logger.info("Deleted collection '%s'", collection)
            except Exception as exc:
                raise StorageError(f"Cannot delete collection '{collection}': {exc}") from exc

    def collection_metadata(self, collection: str) -> dict[str, Any]:
        coll = self._get_or_create_collection(collection)
        metadata = dict(coll.metadata or {})
        metadata.update(self._read_collection_marker(collection))
        return metadata

    def count(self, collection: str = "default") -> int:
        try:
            coll = self._get_or_create_collection(collection)
            return coll.count()
        except Exception:
            return 0

    def get_sources(self, collection: str = "default") -> list[str]:
        """Return unique source file paths in a collection."""
        try:
            coll = self._get_or_create_collection(collection)
            results = coll.get(include=["metadatas"])
            seen: set = set()
            sources: list = []
            for meta in results.get("metadatas", []):
                src = (meta or {}).get("source_id", "")
                file_path = src.rsplit(":", 1)[0] if ":" in src else src
                if file_path and file_path not in seen:
                    seen.add(file_path)
                    sources.append(file_path)
            return sorted(sources)
        except Exception as exc:
            logger.warning("get_sources failed for '%s': %s", collection, exc)
            return []

    def prune(self, collection: str = "default", keep_versions: int = 3) -> int:
        """Remove old chunk versions per source file. Returns count deleted."""
        from collections import defaultdict

        try:
            coll = self._get_or_create_collection(collection)
            results = coll.get(include=["metadatas"])
        except Exception as exc:
            logger.warning("prune: cannot fetch '%s': %s", collection, exc)
            return 0

        ids = results.get("ids", [])
        metas = results.get("metadatas", [])
        if not ids:
            return 0

        version_map: dict = defaultdict(lambda: defaultdict(list))
        for cid, meta in zip(ids, metas):
            meta = meta or {}
            source_id = meta.get("source_id", "")
            file_path = source_id.rsplit(":", 1)[0] if ":" in source_id else source_id
            file_hash = meta.get("file_hash", "unknown")
            if file_path:
                version_map[file_path][file_hash].append(cid)

        ids_to_delete: list = []
        for file_path, hash_to_ids in version_map.items():
            hashes = list(hash_to_ids.keys())
            if len(hashes) <= keep_versions:
                continue
            for fhash in hashes[:-keep_versions]:
                ids_to_delete.extend(hash_to_ids[fhash])

        if ids_to_delete:
            with self._lock:
                self._mark_collection_updating(collection)
                for i in range(0, len(ids_to_delete), 5000):
                    try:
                        coll.delete(ids=ids_to_delete[i : i + 5000])
                    except Exception as exc:
                        logger.warning("prune batch failed: %s", exc)
            logger.info("prune: deleted %d chunks from '%s'", len(ids_to_delete), collection)

        return len(ids_to_delete)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _mutation_marker_path(self, collection: str) -> Path:
        full_name = f"{self._prefix}{collection}"
        digest = hashlib.sha256(full_name.encode("utf-8")).hexdigest()[:16]
        return self._path / f".collection-{digest}.revision.json"

    def _read_collection_marker(self, collection: str) -> dict[str, Any]:
        path = self._mutation_marker_path(collection)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {key: data[key] for key in ("revision", "updated_at") if key in data}

    def _write_collection_marker(self, collection: str, marker: dict[str, Any]) -> None:
        path = self._mutation_marker_path(collection)
        tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp_path.write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    def _mark_collection_updating(self, collection: str) -> None:
        """Advance the persisted mutation marker before changing collection data.

        Marking first can cause an unnecessary BM25 rebuild after a failed
        mutation, but it cannot leave a successfully changed collection looking
        older than its lexical cache.
        """
        current = self._read_collection_marker(collection)
        self._write_collection_marker(
            collection,
            {
                "updated_at": time.time(),
                "revision": int(current.get("revision", 0)) + 1,
            },
        )

    def _make_client(self) -> Any:
        try:
            import chromadb

            return chromadb.PersistentClient(path=str(self._path))
        except ImportError as exc:
            raise StorageError("chromadb required: pip install chromadb") from exc
        except Exception as exc:
            raise StorageError(f"Cannot initialise ChromaDB at {self._path}: {exc}") from exc

    def _get_or_create_collection(self, name: str) -> Any:
        """Get or create a collection with cosine distance and embed model guard (D11, D13)."""
        if name in self._collections:
            return self._collections[name]

        full_name = f"{self._prefix}{name}"
        existing_names = [c.name for c in self._client.list_collections()]

        if full_name in existing_names:
            coll = self._client.get_collection(full_name)
            # D11: verify embedding model has not changed
            stored_model = (coll.metadata or {}).get("embed_model")
            if stored_model and stored_model != self._embed_model:
                raise StorageError(
                    f"Collection '{name}' was built with embed_model='{stored_model}' "
                    f"but current config specifies '{self._embed_model}'. "
                    "Vectors from different models are incompatible. Options:\n"
                    f"  1. Restore original model in config: model: {stored_model}\n"
                    f"  2. Delete and rebuild: pipeline.delete_collection('{name}') "
                    "then re-ingest."
                )
        else:
            # D13: always create with cosine distance
            created_at = time.time()
            meta: dict[str, Any] = {
                "hnsw:space": "cosine",
                "embed_model": self._embed_model,
                "created_at": created_at,
            }
            if self._embed_dimensions is not None:
                meta["embed_dimensions"] = self._embed_dimensions

            coll = self._client.create_collection(
                name=full_name,
                metadata=meta,
            )
            self._write_collection_marker(
                name,
                {"updated_at": created_at, "revision": 0},
            )
            logger.info(
                "Created collection '%s' (model=%s, cosine distance)",
                name,
                self._embed_model,
            )

        self._collections[name] = coll
        return coll


# Import here to avoid circular at module level
import re  # noqa: E402 (used in delete_by_source)
