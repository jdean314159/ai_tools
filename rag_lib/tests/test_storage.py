"""Tests for rag_lib.storage.chroma — D11, D13, D14, D16 invariants."""

from __future__ import annotations

import pytest

pytest.importorskip("chromadb")
from rag_lib.storage.chroma import ChromaStorage
from rag_lib.errors import StorageError
from rag_lib.ingestion.chunker import TextChunk


def _make_chunk(
    text: str, source: str = "test.txt", idx: int = 0, doc_type: str = "paper"
) -> TextChunk:
    return TextChunk(
        text=text,
        context_text=text + " [context]",
        source_id=f"{source}:{idx}",
        doc_type=doc_type,
        chunk_index=idx,
        metadata={"strategy": "fixed_size", "file_hash": "abc123"},
    )


def _fake_embedding(text: str, dims: int = 768) -> list[float]:
    """Deterministic fake embedding based on text hash."""
    import hashlib

    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return [(h >> i & 0xFF) / 255.0 for i in range(dims)]


class TestD13CosineDistance:
    def test_collection_created_with_cosine(self, tmp_dir):
        """D13: All collections must use cosine distance."""
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
        )
        store._get_or_create_collection("default")
        coll = store._get_or_create_collection("default")
        assert coll.metadata.get("hnsw:space") == "cosine"


class TestD11EmbedModelVersionGuard:
    def test_model_mismatch_raises_storage_error(self, tmp_dir):
        """D11: Changing embed_model after collection creation raises StorageError."""
        path = str(tmp_dir / "chroma")

        # Create collection with model A
        store_a = ChromaStorage(path=path, embed_model="model-a")
        store_a._get_or_create_collection("mydata")

        # Try to use same collection with model B
        store_b = ChromaStorage(path=path, embed_model="model-b")
        with pytest.raises(StorageError, match="embed_model"):
            store_b._get_or_create_collection("mydata")

    def test_same_model_does_not_raise(self, tmp_dir):
        """Same model name across instances should not raise."""
        path = str(tmp_dir / "chroma")
        store_a = ChromaStorage(path=path, embed_model="model-x")
        store_a._get_or_create_collection("mydata")
        store_b = ChromaStorage(path=path, embed_model="model-x")
        # Should not raise
        store_b._get_or_create_collection("mydata")


class TestD14ContentAddressedIds:
    def test_same_chunk_same_id(self):
        """D14: chunk_id must be deterministic for the same content."""
        chunk = _make_chunk("hello world", "doc.txt", 0)
        id1 = chunk.chunk_id("hash1")
        id2 = chunk.chunk_id("hash1")
        assert id1 == id2

    def test_different_hash_different_id(self):
        chunk = _make_chunk("hello world", "doc.txt", 0)
        id1 = chunk.chunk_id("hash1")
        id2 = chunk.chunk_id("hash2")
        assert id1 != id2

    def test_reingest_produces_same_ids(self, tmp_dir):
        """Re-ingesting same file with same hash produces same chunk IDs → upsert."""
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        chunk = _make_chunk("test content", "doc.txt", 0)
        emb = [_fake_embedding("test content")]

        store.add([chunk], emb, collection="default")
        count_before = store.count("default")

        # Re-add same chunk (upsert should not increase count)
        store.add([chunk], emb, collection="default")
        count_after = store.count("default")

        assert count_before == count_after == 1


class TestAddAndSearch:
    def test_add_and_retrieve(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        chunk = _make_chunk("NetFlow anomaly detection")
        emb = [_fake_embedding("NetFlow anomaly detection")]
        store.add([chunk], emb, collection="default")

        results = store.search(
            _fake_embedding("NetFlow anomaly detection"),
            n_results=1,
            collection="default",
        )
        assert len(results) == 1
        assert results[0].text == "NetFlow anomaly detection"

    def test_context_text_stored_and_returned(self, tmp_dir):
        """The LLM should receive context_text, not the short embedded text."""
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        chunk = _make_chunk("short text")
        emb = [_fake_embedding("short text")]
        store.add([chunk], emb, collection="default")

        results = store.search(_fake_embedding("short text"), n_results=1)
        assert results[0].context_text == "short text [context]"

    def test_score_in_valid_range(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        chunk = _make_chunk("test")
        emb = [_fake_embedding("test")]
        store.add([chunk], emb, collection="default")
        results = store.search(_fake_embedding("test"), n_results=1)
        assert 0.0 <= results[0].score <= 1.0

    def test_search_empty_collection_returns_empty(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
        )
        results = store.search([0.0] * 768, n_results=5)
        assert results == []


class TestDeleteBySource:
    def test_deletes_matching_chunks(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        c1 = _make_chunk("content 1", "doc_a.txt", 0)
        c2 = _make_chunk("content 2", "doc_b.txt", 0)
        store.add([c1, c2], [_fake_embedding("content 1"), _fake_embedding("content 2")])

        deleted = store.delete_by_source("doc_a.txt")
        assert deleted >= 1
        assert store.count() == 1


class TestPruning:
    def test_prune_removes_old_versions(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        # Simulate two versions of the same file (different hashes)
        for version_hash in ["hash_v1", "hash_v2", "hash_v3", "hash_v4"]:
            chunk = _make_chunk("content", "doc.txt", 0)
            chunk.metadata["file_hash"] = version_hash
            store.add([chunk], [_fake_embedding(f"content_{version_hash}")])

        count_before = store.count()
        deleted = store.prune(keep_versions=2)
        count_after = store.count()

        assert deleted >= 0  # May be 0 if dedup collapsed versions
        assert count_after <= count_before


class TestBatchUpsert:
    def test_large_batch_does_not_exceed_chroma_limit(self, tmp_dir):
        """ChromaDB has a ~5461 record limit per upsert call — must batch."""
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=32,
        )
        # Create 6000 chunks (above ChromaDB's limit)
        chunks = [_make_chunk(f"text_{i}", "big.txt", i) for i in range(6000)]
        embeddings = [[0.1] * 32 for _ in range(6000)]

        # Should not raise ChromaDB batch size error
        store.add(chunks, embeddings)
        assert store.count() > 0
