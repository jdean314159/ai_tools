"""
rag_lib.retrieval.retriever

Two-stage hybrid retrieval:
  Stage 1: BM25 (rank_bm25) + ChromaDB dense → 50 candidates via RRF.
  Stage 2: Cross-encoder reranking (optional, see reranker.py) → top N.

D5: BM25 + dense + RRF in Stage 1.
D8: assemble_prompt() fills chunks by score until max_context_tokens is spent.
D12: BM25 index persisted to disk; rebuilt only when ChromaDB is newer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from ..errors import RagLibError
from ..storage.base import StoredChunk

logger = logging.getLogger(__name__)

_RRF_K = 60  # standard constant for Reciprocal Rank Fusion


class HybridRetriever:
    """Hybrid BM25 + dense vector retrieval with Reciprocal Rank Fusion.

    Args:
        store:         ChromaStorage instance.
        embedder:      OllamaEmbedder instance.
        bm25_path:     Directory for persisting BM25 indexes.
        n_candidates:  Stage 1 retrieval count (BM25 + dense combined).
        n_results:     Final result count after budget enforcement.
        bm25_weight:   RRF weight for BM25 (0.4); dense gets (1 - bm25_weight).
        parent_window: Unused in retriever (context_text already set by chunker).
        max_context_tokens: Token budget for assemble_prompt().
    """

    def __init__(
        self,
        store: Any,
        embedder: Any,
        bm25_path: str | Path = "~/.rag_lib/bm25",
        n_candidates: int = 50,
        n_results: int = 5,
        bm25_weight: float = 0.4,
        parent_window: int = 3,
        max_context_tokens: int = 3000,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._bm25_path = Path(bm25_path).expanduser()
        self._bm25_path.mkdir(parents=True, exist_ok=True)
        self._n_candidates = n_candidates
        self._n_results = n_results
        self._bm25_weight = bm25_weight
        self._max_context_tokens = max_context_tokens
        self._bm25_indexes: dict[str, Any] = {}
        self._bm25_corpus: dict[str, list[str]] = {}
        self._bm25_ids: dict[str, list[str]] = {}
        self._bm25_built_at: dict[str, float] = {}

    def _bm25_results_to_chunks(
        self,
        bm25: list[tuple[str, float]],
        dense_results: list[StoredChunk],
        collection: str,
    ) -> tuple[list[StoredChunk], list[str]]:
        dense_map = {chunk.chunk_id: chunk for chunk in dense_results}
        bm25_only_ids = [chunk_id for chunk_id, _score in bm25 if chunk_id not in dense_map]
        materialized: list[StoredChunk] = []

        get_by_ids = getattr(self._store, "get_by_ids", None)
        if bm25_only_ids and callable(get_by_ids):
            try:
                materialized = get_by_ids(bm25_only_ids, collection=collection)
            except Exception as exc:
                logger.warning(
                    "Cannot materialize BM25-only candidates for '%s' by ID: %s",
                    collection,
                    exc,
                )
        elif bm25_only_ids:
            # Compatibility path for VectorStore implementations that predate
            # exact ID lookup. This uses the existing bounded collection scan.
            try:
                materialized = self._load_all_chunks_from_store(collection)
            except Exception as exc:
                logger.warning(
                    "Cannot materialize BM25-only candidates for '%s' by scan: %s",
                    collection,
                    exc,
                )

        chunk_map = {**dense_map, **{chunk.chunk_id: chunk for chunk in materialized}}
        results: list[StoredChunk] = []
        missing_ids: list[str] = []
        for rank, (chunk_id, score) in enumerate(bm25, start=1):
            chunk = chunk_map.get(chunk_id)
            if chunk is not None:
                results.append(
                    StoredChunk(
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        context_text=chunk.context_text,
                        score=round(float(score), 6),
                        source_id=chunk.source_id,
                        doc_type=chunk.doc_type,
                        metadata={**chunk.metadata, "bm25_rank": rank},
                    )
                )
            else:
                missing_ids.append(chunk_id)
        return results, missing_ids

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve_with_details(
        self,
        query: str,
        collection: str = "default",
    ) -> dict[str, Any]:
        """Retrieve top chunks and return intermediate retrieval stages for inspection."""
        query_vec = self._embedder.embed_query(query)
        if not query_vec:
            logger.warning("Embedder returned empty vector for query: %r", query[:80])
            return {
                "query": query,
                "collection": collection,
                "dense_results": [],
                "bm25_results": [],
                "fused_results": [],
                "warnings": ["empty_query_vector"],
                "diagnostics": {"dense_count": 0, "bm25_count": 0, "fused_count": 0},
            }

        dense_results = self._store.search(
            query_vector=query_vec,
            n_results=self._n_candidates,
            collection=collection,
        )

        bm25_error: str | None = None
        try:
            bm25_index, corpus_ids = self._get_bm25_index(collection)
            bm25_scores = self._bm25_search(query, bm25_index, corpus_ids, collection)
        except Exception as exc:
            bm25_scores = []
            bm25_error = f"{type(exc).__name__}: {exc}"
            logger.warning("BM25 search failed for '%s': %s", collection, exc)
        bm25_results, missing_bm25_ids = self._bm25_results_to_chunks(
            bm25_scores,
            dense_results,
            collection,
        )
        fused = self._reciprocal_rank_fusion(dense_results, bm25_results)
        final = fused[: self._n_candidates]

        dense_ids = {chunk.chunk_id for chunk in dense_results}
        bm25_ids = {cid for cid, _ in bm25_scores}
        warnings: list[str] = []
        if bm25_error is not None:
            warnings.append("bm25_search_failed")
        if missing_bm25_ids:
            warnings.append("bm25_candidates_unmaterialized")
            logger.warning(
                "Could not materialize %d BM25 candidate(s) for '%s': %s",
                len(missing_bm25_ids),
                collection,
                ", ".join(missing_bm25_ids),
            )

        return {
            "query": query,
            "collection": collection,
            "dense_results": dense_results,
            "bm25_results": bm25_results,
            "fused_results": final,
            "warnings": warnings,
            "diagnostics": {
                "dense_count": len(dense_results),
                "bm25_count": len(bm25_scores),
                "fused_count": len(final),
                "dense_only_candidates": sum(
                    1 for chunk in final if chunk.chunk_id not in bm25_ids
                ),
                "bm25_only_candidates": sum(1 for cid in bm25_ids if cid not in dense_ids),
                "bm25_unmaterialized_count": len(missing_bm25_ids),
                "bm25_unmaterialized_chunk_ids": missing_bm25_ids,
                "bm25_search_error": bm25_error,
            },
        }

    def retrieve(
        self,
        query: str,
        collection: str = "default",
    ) -> list[StoredChunk]:
        details = self.retrieve_with_details(query, collection=collection)
        return list(details.get("fused_results", []))[: self._n_results]

    def assemble_prompt_with_selection(
        self,
        query: str,
        chunks: list[StoredChunk],
        max_context_tokens: int | None = None,
        system_prompt: str = "",
    ) -> tuple[str, list[StoredChunk], dict[str, Any]]:
        budget = max_context_tokens if max_context_tokens is not None else self._max_context_tokens
        if max_context_tokens is None:
            logger.warning(
                "assemble_prompt called without max_context_tokens. "
                "Using config default (%d). Set this based on your model's context window.",
                self._max_context_tokens,
            )

        overhead = len(query.split()) + 50
        if system_prompt:
            overhead += len(system_prompt.split())
        available = max(0, budget - overhead)

        selected: list[StoredChunk] = []
        for chunk in chunks:
            cost = len(chunk.context_text.split())
            if cost <= available:
                selected.append(chunk)
                available -= cost

        if not selected:
            logger.warning(
                "No chunks fit within token budget (budget=%d, overhead=%d, "
                "first chunk size=%d). Returning prompt with query only.",
                budget,
                overhead,
                len(chunks[0].context_text.split()) if chunks else 0,
            )

        parts: list[str] = []
        if system_prompt.strip():
            parts.append(system_prompt.strip())

        if selected:
            context_items = [f"[{i + 1}] {c.context_text}" for i, c in enumerate(selected)]
            parts.append("Context:\n" + "\n\n".join(context_items))

        parts.append(f"Question: {query}\n\nAnswer:")
        prompt = "\n\n".join(parts)
        diagnostics = {
            "budget": budget,
            "overhead": overhead,
            "unused_context_tokens": available,
            "selected_chunk_ids": [chunk.chunk_id for chunk in selected],
            "selected_count": len(selected),
            "candidate_count": len(chunks),
        }
        return prompt, selected, diagnostics

    def assemble_prompt(
        self,
        query: str,
        chunks: list[StoredChunk],
        max_context_tokens: int | None = None,
        system_prompt: str = "",
    ) -> str:
        prompt, _selected, _diagnostics = self.assemble_prompt_with_selection(
            query=query,
            chunks=chunks,
            max_context_tokens=max_context_tokens,
            system_prompt=system_prompt,
        )
        return prompt

    def build_bm25_index(
        self,
        chunks: list[StoredChunk],
        collection: str = "default",
    ) -> None:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise RagLibError("rank_bm25 required: pip install rank_bm25") from exc

        corpus = [c.text for c in chunks]
        ids = [c.chunk_id for c in chunks]
        tokenized = [doc.lower().split() for doc in corpus]
        index = BM25Okapi(tokenized)

        self._bm25_indexes[collection] = index
        self._bm25_corpus[collection] = corpus
        self._bm25_ids[collection] = ids

        # Persist data only (no pickle): the BM25 index is a pure function of
        # the corpus, so we cache corpus+ids as JSON and rebuild the index on
        # load. This removes the arbitrary-code-execution surface exposed by
        # executable deserialization if the cache file is ever attacker-writable.
        built_at = time.time()
        self._bm25_built_at[collection] = built_at
        json_path = self._bm25_path / f"{collection}.json"
        tmp_path = json_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"corpus": corpus, "ids": ids, "built_at": built_at}, f)
        tmp_path.replace(json_path)
        logger.debug("BM25 index persisted for collection '%s' (%d docs)", collection, len(corpus))

    def lexical_state_inventory(self, collection: str = "default") -> dict[str, Any]:
        """Return a text-free digest inventory of the active BM25 source state.

        Calling this method loads or rebuilds a stale lexical index through the
        same path retrieval uses. Records preserve corpus order because equal
        BM25 scores retain that order during ranking.
        """

        index, ids = self._get_bm25_index(collection)
        if index is None or not ids:
            return {
                "digest_method": "utf8-corpus-order-v1",
                "tokenization": "unicode-lower-whitespace-split-v1",
                "records": [],
            }
        corpus = self._bm25_corpus.get(collection)
        if not isinstance(corpus, list) or len(corpus) != len(ids):
            raise RagLibError("BM25 corpus and id counts differ")
        if len(set(ids)) != len(ids):
            raise RagLibError("BM25 state contains duplicate chunk ids")
        records: list[dict[str, Any]] = []
        for position, (chunk_id, text) in enumerate(zip(ids, corpus)):
            if not isinstance(chunk_id, str) or not chunk_id:
                raise RagLibError("BM25 state contains an invalid chunk id")
            if not isinstance(text, str):
                raise RagLibError("BM25 state contains a non-text corpus value")
            records.append(
                {
                    "position": position,
                    "chunk_id": chunk_id,
                    "text_digest": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
            )
        return {
            "digest_method": "utf8-corpus-order-v1",
            "tokenization": "unicode-lower-whitespace-split-v1",
            "records": records,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _get_bm25_index(self, collection: str) -> tuple[Any, list[str]]:
        """Load BM25 index from cache or disk; rebuild from ChromaDB if stale."""
        if collection in self._bm25_indexes:
            ids = self._bm25_ids.get(collection, [])
            if not self._bm25_cache_is_stale(
                collection,
                ids=ids,
                built_at=self._bm25_built_at.get(collection),
            ):
                return self._bm25_indexes[collection], ids
            self._discard_bm25_memory_cache(collection)

        json_path = self._bm25_path / f"{collection}.json"
        if json_path.exists():
            try:
                from rank_bm25 import BM25Okapi

                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                corpus = data["corpus"]
                ids = data["ids"]
                built_at = data.get("built_at")
                if self._bm25_cache_is_stale(collection, ids=ids, built_at=built_at):
                    logger.info("BM25 cache stale for '%s'; rebuilding.", collection)
                else:
                    tokenized = [doc.lower().split() for doc in corpus]
                    index = BM25Okapi(tokenized)
                    self._bm25_indexes[collection] = index
                    self._bm25_corpus[collection] = corpus
                    self._bm25_ids[collection] = ids
                    if built_at is not None:
                        self._bm25_built_at[collection] = float(built_at)
                    logger.debug("BM25 index loaded (rebuilt from JSON) for '%s'", collection)
                    return index, ids
            except Exception as exc:
                logger.warning("BM25 cache unreadable for '%s': %s. Rebuilding.", collection, exc)

        # No index yet: build from ChromaDB on demand
        logger.info("BM25 index not found for '%s'; building from ChromaDB...", collection)
        all_chunks = self._load_all_chunks_from_store(collection)
        if all_chunks:
            self.build_bm25_index(all_chunks, collection)
            return self._bm25_indexes[collection], self._bm25_ids[collection]

        # Empty collection — return a null index
        logger.debug("Collection '%s' is empty; BM25 not built.", collection)
        return None, []

    def _discard_bm25_memory_cache(self, collection: str) -> None:
        self._bm25_indexes.pop(collection, None)
        self._bm25_corpus.pop(collection, None)
        self._bm25_ids.pop(collection, None)
        self._bm25_built_at.pop(collection, None)

    def _bm25_cache_is_stale(
        self,
        collection: str,
        *,
        ids: list[str],
        built_at: Any,
    ) -> bool:
        """Compare a lexical cache with persisted vector-store mutation state."""
        try:
            store_count = self._store.count(collection)
        except Exception as exc:
            logger.warning("Cannot validate BM25 count for '%s': %s", collection, exc)
            return True
        else:
            if isinstance(store_count, int) and store_count != len(ids):
                return True

        try:
            metadata = self._store.collection_metadata(collection)
        except Exception as exc:
            logger.warning("Cannot validate BM25 timestamp for '%s': %s", collection, exc)
            return True
        if not isinstance(metadata, Mapping):
            return False

        updated_at = metadata.get("updated_at")
        if updated_at is None:
            return False
        if built_at is None:
            return True
        try:
            return float(updated_at) > float(built_at)
        except (TypeError, ValueError):
            logger.warning("Invalid BM25/store timestamps for '%s'; rebuilding.", collection)
            return True

    def _load_all_chunks_from_store(self, collection: str) -> list[StoredChunk]:
        """Retrieve all chunks from ChromaDB for BM25 index building."""
        # Storage failures propagate so callers can record lexical-channel
        # degradation instead of treating a broken store as an empty corpus.
        dims = self._embedder.dimensions()
        zero_vec = [0.0] * dims
        count = self._store.count(collection)
        if count == 0:
            return []
        return self._store.search(zero_vec, n_results=min(count, 10_000), collection=collection)

    def _bm25_search(
        self,
        query: str,
        index: Any,
        corpus_ids: list[str],
        collection: str,
    ) -> list[tuple[str, float]]:
        """Return (chunk_id, score) pairs from BM25 search."""
        if index is None or not corpus_ids:
            return []
        scores = index.get_scores(query.lower().split())
        ranked = sorted(
            zip(corpus_ids, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[: self._n_candidates]

    def _reciprocal_rank_fusion(
        self,
        dense: list[StoredChunk],
        bm25: list[StoredChunk],
    ) -> list[StoredChunk]:
        """Combine dense and BM25 rankings via Reciprocal Rank Fusion.

        RRF score = sum(1 / (k + rank_i)) across all result lists.
        k=60 is the standard constant.
        """
        rrf_scores: dict[str, float] = {}

        # Dense ranking
        for rank, chunk in enumerate(dense, start=1):
            rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0)
            rrf_scores[chunk.chunk_id] += (1.0 - self._bm25_weight) / (_RRF_K + rank)

        # BM25 ranking
        for fallback_rank, chunk in enumerate(bm25, start=1):
            rank = chunk.metadata.get("bm25_rank", fallback_rank)
            cid = chunk.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0)
            rrf_scores[cid] += self._bm25_weight / (_RRF_K + rank)

        # Build a lookup from chunk_id → StoredChunk for both channels.
        dense_map = {c.chunk_id: c for c in dense}
        bm25_map = {c.chunk_id: c for c in bm25}
        dense_ranks = {chunk.chunk_id: rank for rank, chunk in enumerate(dense, start=1)}
        bm25_ranks = {
            chunk.chunk_id: chunk.metadata.get("bm25_rank", fallback_rank)
            for fallback_rank, chunk in enumerate(bm25, start=1)
        }

        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
        result: list[StoredChunk] = []
        for cid in sorted_ids:
            chunk = dense_map.get(cid) or bm25_map[cid]
            metadata = dict(chunk.metadata)
            if cid in dense_ranks:
                metadata["dense_rank"] = dense_ranks[cid]
            if cid in bm25_ranks:
                metadata["bm25_rank"] = bm25_ranks[cid]
            metadata["retrieval_channels"] = [
                channel
                for channel, channel_map in (("dense", dense_map), ("bm25", bm25_map))
                if cid in channel_map
            ]
            result.append(
                replace(
                    chunk,
                    score=round(rrf_scores[cid], 6),
                    metadata=metadata,
                )
            )
        return result
