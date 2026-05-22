"""Tests for ChromaDBStore."""
from __future__ import annotations
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


def make_store(tmp_path, dim=8, name="test_collection"):
    """Create a ChromaDBStore with mock chromadb."""
    try:
        from engram.storage.chromadb_store import ChromaDBStore
        return ChromaDBStore(
            persist_directory=tmp_path / "chroma",
            collection_name=name,
            embedding_dimension=dim,
        )
    except ImportError:
        pytest.skip("chromadb not installed")


class FakeEmbedder:
    """Minimal embedder for ChromaDB tests."""
    DIMENSION = 8
    model_name = "fake:test"
    dimension = DIMENSION

    def embed(self, text):
        from tests.conftest import MockEmbedder
        return MockEmbedder().embed(text)

    def embed_batch(self, texts):
        from tests.conftest import MockEmbedder
        return MockEmbedder().embed_batch(texts)


# Skip all tests if chromadb not installed
pytestmark = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("chromadb"),
    reason="chromadb not installed",
)


def test_add_and_query(tmp_path):
    store = make_store(tmp_path)
    embedding = [0.1] * 8
    store.add("ep_001", "test episode text", embedding, {"importance": 0.8})
    assert store.count() == 1

    results = store.query(embedding, n=5)
    assert len(results["ids"][0]) == 1
    assert results["ids"][0][0] == "ep_001"
    assert results["documents"][0][0] == "test episode text"


def test_add_batch(tmp_path):
    store = make_store(tmp_path)
    ids = ["ep_001", "ep_002", "ep_003"]
    texts = ["first episode", "second episode", "third episode"]
    embeddings = [[0.1 * (i + 1)] * 8 for i in range(3)]

    store.add_batch(episode_ids=ids, texts=texts, embeddings=embeddings)
    assert store.count() == 3


def test_delete(tmp_path):
    store = make_store(tmp_path)
    store.add("ep_001", "episode to delete", [0.1] * 8)
    assert store.count() == 1
    store.delete("ep_001")
    assert store.count() == 0


def test_query_empty_collection(tmp_path):
    """Query on empty collection returns empty results without error."""
    store = make_store(tmp_path)
    results = store.query([0.1] * 8, n=5)
    assert results["ids"] == [[]]
    assert results["documents"] == [[]]


def test_n_capped_at_count(tmp_path):
    """n_results is capped at collection size."""
    store = make_store(tmp_path)
    store.add("ep_001", "only episode", [0.1] * 8)
    # Requesting more than available should not raise
    results = store.query([0.1] * 8, n=100)
    assert len(results["ids"][0]) == 1


def test_dimension_mismatch_raises(tmp_path):
    """Opening existing collection with wrong dimension raises DimensionMismatchError."""
    from engram.storage.chromadb_store import ChromaDBStore, DimensionMismatchError

    # Create with 8-dim
    s1 = ChromaDBStore(tmp_path / "chroma", "col", embedding_dimension=8)
    s1.add("ep_001", "text", [0.1] * 8)

    # Reopen with 16-dim — should raise
    with pytest.raises(DimensionMismatchError) as exc:
        ChromaDBStore(tmp_path / "chroma", "col", embedding_dimension=16)
    assert "8" in str(exc.value) or "mismatch" in str(exc.value).lower()


def test_dimension_mismatch_message_is_helpful(tmp_path):
    """Error message should tell user what to do."""
    from engram.storage.chromadb_store import ChromaDBStore, DimensionMismatchError

    ChromaDBStore(tmp_path / "chroma", "col", embedding_dimension=8)
    try:
        ChromaDBStore(tmp_path / "chroma", "col", embedding_dimension=32)
    except DimensionMismatchError as e:
        assert "migrate" in str(e).lower() or "rebuild" in str(e).lower()


def test_new_collection_no_mismatch(tmp_path):
    """New collection with any dimension is fine."""
    from engram.storage.chromadb_store import ChromaDBStore
    store = ChromaDBStore(tmp_path / "chroma", "new_col", embedding_dimension=1024)
    assert store.count() == 0


def test_metadata_sanitization(tmp_path):
    """Complex metadata types are serialized to strings."""
    store = make_store(tmp_path)
    store.add(
        "ep_001", "text", [0.1] * 8,
        metadata={
            "list_val": [1, 2, 3],
            "dict_val": {"key": "val"},
            "none_val": None,
            "str_val": "hello",
            "int_val": 42,
            "float_val": 0.5,
            "bool_val": True,
        }
    )
    results = store.query([0.1] * 8, n=1)
    meta = results["metadatas"][0][0]
    assert meta["str_val"] == "hello"
    assert meta["int_val"] == 42
    assert "none_val" not in meta  # None dropped


def test_rebuild_from_episodes(tmp_path):
    """rebuild_from_episodes repopulates collection from episode list."""
    store = make_store(tmp_path)
    embedder = FakeEmbedder()

    episodes = [
        {"id": "ep_001", "text": "first episode about python"},
        {"id": "ep_002", "text": "second episode about java"},
        {"id": "ep_003", "text": "third episode about rust"},
    ]
    store.rebuild_from_episodes(episodes, embedder, batch_size=2)
    assert store.count() == 3

    results = store.query(embedder.embed("python").embedding, n=3)
    assert len(results["ids"][0]) == 3


def test_add_wrong_dimension_raises(tmp_path):
    """Adding vector with wrong dimension raises ValueError."""
    store = make_store(tmp_path, dim=8)
    with pytest.raises(ValueError) as exc:
        store.add("ep_001", "text", [0.1] * 16)  # Wrong dim
    assert "dimension" in str(exc.value).lower()
