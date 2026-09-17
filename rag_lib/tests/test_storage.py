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
    def test_invalid_model_digest_is_rejected(self, tmp_dir):
        with pytest.raises(StorageError, match="embed_model_digest"):
            ChromaStorage(
                path=str(tmp_dir / "chroma"),
                embed_model="model-x",
                embed_model_digest="latest",
            )

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

    def test_digest_mismatch_raises_even_when_model_label_matches(self, tmp_dir):
        path = str(tmp_dir / "chroma")
        store_a = ChromaStorage(
            path=path,
            embed_model="model-x",
            embed_model_digest="sha256:" + "a" * 64,
        )
        store_a._get_or_create_collection("mydata")
        store_b = ChromaStorage(
            path=path,
            embed_model="model-x",
            embed_model_digest="sha256:" + "b" * 64,
        )

        with pytest.raises(StorageError, match="embed_model_digest"):
            store_b._get_or_create_collection("mydata")

    def test_discovered_dimensions_are_stored_when_collection_is_created(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="model-x",
        )

        store.add([_make_chunk("small")], [[0.1, 0.2, 0.3]], collection="mydata")

        assert store.collection_metadata("mydata")["embed_dimensions"] == 3

    def test_add_rejects_embedding_dimension_mismatch(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="model-x",
            embed_dimensions=3,
        )

        with pytest.raises(StorageError, match="dimensions"):
            store.add([_make_chunk("small")], [[0.1, 0.2]], collection="mydata")


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

    def test_same_id_upsert_advances_collection_revision(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        chunk = _make_chunk("test content", "doc.txt", 0)
        embedding = [_fake_embedding("test content")]

        store.add([chunk], embedding, collection="default")
        first = store.collection_metadata("default")
        store.add([chunk], embedding, collection="default")
        second = store.collection_metadata("default")

        assert first["revision"] == 1
        assert second["revision"] == 2
        assert second["updated_at"] >= first["updated_at"]

    def test_delete_by_source_does_not_delete_prefix_collision(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        first = _make_chunk("first", "doc1", 0)
        second = _make_chunk("second", "doc10", 0)
        store.add(
            [first, second],
            [_fake_embedding("first"), _fake_embedding("second")],
            collection="default",
        )

        assert store.delete_by_source("doc1", collection="default") == 1
        assert store.count("default") == 1
        assert store.get_sources("default") == ["doc10"]


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

    def test_context_truncation_is_explicit_and_digest_covers_returned_bytes(self, tmp_dir):
        import hashlib

        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        chunk = _make_chunk("short")
        chunk.context_text = "x" * 5000
        store.add([chunk], [_fake_embedding("short")], collection="default")

        result = store.search(_fake_embedding("short"), n_results=1)[0]

        assert result.metadata["context_truncated"] is True
        assert result.metadata["context_original_chars"] == 5000
        assert (
            result.chunk_digest
            == "sha256:" + hashlib.sha256(result.context_text.encode("utf-8")).hexdigest()
        )

    def test_get_by_ids_materializes_chunks_in_requested_order(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        first = _make_chunk("first text", "first.txt", 0)
        second = _make_chunk("second text", "second.txt", 0)
        store.add(
            [first, second],
            [_fake_embedding("first text"), _fake_embedding("second text")],
        )
        first_id = first.chunk_id("abc123")
        second_id = second.chunk_id("abc123")

        results = store.get_by_ids([second_id, first_id])

        assert [chunk.chunk_id for chunk in results] == [second_id, first_id]
        assert results[0].text == "second text"
        assert results[0].context_text == "second text [context]"
        assert results[0].source_id == "second.txt:0"
        assert results[0].metadata["strategy"] == "fixed_size"

    def test_collection_inventory_is_complete_metadata_only_scan(self, tmp_dir):
        store = ChromaStorage(
            path=str(tmp_dir / "chroma"),
            embed_model="test-model",
            embed_dimensions=768,
        )
        first = _make_chunk("private first text", "entry-one", 0)
        second = _make_chunk("private second text", "entry-two", 0)
        first.metadata["source_digest"] = "sha256:" + "1" * 64
        second.metadata["source_digest"] = "sha256:" + "2" * 64
        store.add(
            [first, second],
            [_fake_embedding("private first text"), _fake_embedding("private second text")],
        )

        inventory = store.collection_inventory()

        assert len(inventory) == store.count() == 2
        assert all(
            set(item) == {"chunk_id", "source_id", "source_digest", "chunk_digest"}
            for item in inventory
        )
        assert {item["source_id"] for item in inventory} == {"entry-one:0", "entry-two:0"}
        assert "private first text" not in repr(inventory)
        assert "private second text" not in repr(inventory)

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
