"""
Integration tests requiring a running Ollama instance.

These tests are skipped automatically if Ollama is not running or if
the required model is not pulled. To run:

    pytest tests/test_ollama_integration.py -v

Requirements:
    ollama pull nomic-embed-text
    ollama pull qwen3.5:9b  (optional, for extractor tests)
"""
from __future__ import annotations
import tempfile
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures / skip helpers
# ---------------------------------------------------------------------------

def _ollama_available() -> bool:
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _model_available(model_name: str) -> bool:
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        tags = r.json().get("models", [])
        return any(m.get("name", "").startswith(model_name.split(":")[0]) for m in tags)
    except Exception:
        return False


requires_ollama = pytest.mark.skipif(
    not _ollama_available(),
    reason="Ollama not running at localhost:11434",
)

requires_nomic = pytest.mark.skipif(
    not _ollama_available() or not _model_available("nomic-embed-text"),
    reason="nomic-embed-text not available. Run: ollama pull nomic-embed-text",
)


@pytest.fixture
def ollama_embedder():
    from engram_lite.embeddings.ollama import OllamaEmbedder
    return OllamaEmbedder(model="nomic-embed-text")


@pytest.fixture
def memory_with_real_embedder(tmp_path, ollama_embedder):
    from engram_lite import ProjectMemory
    mem = ProjectMemory(
        base_dir=tmp_path,
        project_id="integration_test",
        session_id="s1",
        embedder=ollama_embedder,
        auto_pair_assistant=True,
        enable_semantic_graph=True,
    )
    yield mem
    mem.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@requires_nomic
def test_real_embedder_dimension(ollama_embedder):
    """nomic-embed-text should produce 768-dim vectors."""
    result = ollama_embedder.embed("test text for dimension check")
    assert len(result.embedding) == 768
    assert result.model == "ollama:nomic-embed-text"
    assert result.dimension == 768


@requires_nomic
def test_embedding_cache_reduces_ollama_calls(tmp_path, ollama_embedder):
    """Cache should prevent redundant Ollama calls."""
    from engram_lite.embeddings.cache import EmbeddingCache, CachedEmbedder

    cache = EmbeddingCache(tmp_path / "cache.db")
    cached = CachedEmbedder(ollama_embedder, cache)

    text = "This is a test sentence for cache verification."

    # First call: miss
    r1 = cached.embed(text)
    assert cached.misses == 1
    assert cached.hits == 0

    # Second call: hit
    r2 = cached.embed(text)
    assert cached.hits == 1
    assert cached.misses == 1

    # Embeddings should be identical
    assert r1.embedding == r2.embedding


@requires_nomic
def test_full_workflow_with_real_embedder(memory_with_real_embedder):
    """Add turns, search, verify hybrid retrieval works."""
    mem = memory_with_real_embedder

    # Add conversation about Python web scraping
    mem.add_turn("user", "I am building a web scraper for job listings.", "s1")
    mem.add_turn("assistant", "Great, are you using BeautifulSoup or Scrapy?", "s1")
    mem.add_turn("user", "I prefer BeautifulSoup for its simplicity.", "s1")
    mem.add_turn("assistant", "Good choice, it works well for static HTML.", "s1")

    # Search by semantic similarity (not just keyword)
    results = mem.search_episodes("HTML parsing library", n=5)
    assert len(results) > 0

    # Check paired exchange is retrievable
    stats = mem.get_stats()
    assert stats["episodic"]["pairing"]["paired_exchanges"] >= 2
    assert stats["vector_search"]["available"] is True


@requires_nomic
def test_persistence_across_reopen_with_embeddings(tmp_path, ollama_embedder):
    """Close memory, reopen, verify ChromaDB persists."""
    from engram_lite import ProjectMemory

    # First session
    mem1 = ProjectMemory(
        base_dir=tmp_path, project_id="persist_test", session_id="s1",
        embedder=ollama_embedder,
    )
    mem1.add_turn("user", "Remember that I prefer dark mode in all editors.", "s1")
    count_before = len(mem1._episodes)
    mem1.close()

    # Reopen
    from engram_lite.embeddings.ollama import OllamaEmbedder
    mem2 = ProjectMemory(
        base_dir=tmp_path, project_id="persist_test", session_id="s1",
        embedder=OllamaEmbedder(model="nomic-embed-text"),
    )
    assert len(mem2._episodes) == count_before
    assert mem2.chromadb is not None
    assert mem2.chromadb.count() == count_before
    results = mem2.search_episodes("editor preferences", n=5)
    assert len(results) > 0
    mem2.close()


@requires_nomic
def test_dimension_mismatch_raises_error(tmp_path, ollama_embedder):
    """Switching to incompatible embedder should raise DimensionMismatchError."""
    from engram_lite import ProjectMemory
    from engram_lite.storage.chromadb_store import DimensionMismatchError

    # Create with real 768-dim embedder
    mem = ProjectMemory(
        base_dir=tmp_path, project_id="dim_test", session_id="s1",
        embedder=ollama_embedder,
    )
    mem.store_episode(
        "Testing dimension mismatch detection with real embedder.",
        importance=0.8,
        bypass_filter=True,
    )
    mem.close()

    # Reopen with mock 8-dim embedder — should raise DimensionMismatchError
    from tests.conftest import MockEmbedder
    with pytest.raises(DimensionMismatchError) as exc_info:
        mem2 = ProjectMemory(
            base_dir=tmp_path, project_id="dim_test", session_id="s1",
            embedder=MockEmbedder(),
        )
        mem2.close()

    assert "768" in str(exc_info.value) or "mismatch" in str(exc_info.value).lower()


@requires_nomic
def test_deletion_with_chromadb(memory_with_real_embedder):
    """delete_episode should remove from both JSONL and ChromaDB."""
    mem = memory_with_real_embedder

    eid = mem.store_episode(
        "This episode will be deleted to verify cleanup.",
        importance=0.9,
        bypass_filter=True,
    )
    assert eid

    chroma_count_before = mem.chromadb.count()
    episode_count_before = len(mem._episodes)

    deleted = mem.delete_episode(eid)
    assert deleted is True
    assert len(mem._episodes) == episode_count_before - 1
    assert mem.chromadb.count() == chroma_count_before - 1


@requires_nomic
def test_forget_session(memory_with_real_embedder):
    """forget_session should remove turns and related episodes."""
    mem = memory_with_real_embedder

    mem.add_turn("user", "Start of session to be forgotten.", "s1")
    mem.add_turn("assistant", "Acknowledged.", "s1")

    episodes_before = len(mem._episodes)
    result = mem.forget_session("s1")

    assert result["turns_removed"] >= 2
    assert len(mem._episodes) <= episodes_before
