"""Tests for EmbeddingCache and CachedEmbedder."""
from __future__ import annotations
import tempfile
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# EmbeddingCache unit tests
# ---------------------------------------------------------------------------

def test_cache_miss_returns_none(tmp_path):
    from engram.embeddings.cache import EmbeddingCache
    cache = EmbeddingCache(tmp_path / "cache.db")
    result = cache.get("unseen text", "model:test")
    assert result is None


def test_cache_put_and_get(tmp_path):
    from engram.embeddings.cache import EmbeddingCache
    from engram.embeddings.base import EmbeddingResult

    cache = EmbeddingCache(tmp_path / "cache.db")
    embedding = [0.1, 0.2, 0.3, 0.4]
    result = EmbeddingResult(
        text="hello world",
        embedding=embedding,
        model="model:test",
        dimension=4,
    )
    cache.put(result)

    retrieved = cache.get("hello world", "model:test")
    assert retrieved == embedding


def test_cache_different_models_isolated(tmp_path):
    """Same text, different model names = different cache entries."""
    from engram.embeddings.cache import EmbeddingCache
    from engram.embeddings.base import EmbeddingResult

    cache = EmbeddingCache(tmp_path / "cache.db")
    text = "shared text"

    cache.put(EmbeddingResult(text=text, embedding=[1.0, 0.0], model="model:a", dimension=2))
    cache.put(EmbeddingResult(text=text, embedding=[0.0, 1.0], model="model:b", dimension=2))

    assert cache.get(text, "model:a") == [1.0, 0.0]
    assert cache.get(text, "model:b") == [0.0, 1.0]


def test_cache_put_overwrites(tmp_path):
    """Second put for same key replaces first."""
    from engram.embeddings.cache import EmbeddingCache
    from engram.embeddings.base import EmbeddingResult

    cache = EmbeddingCache(tmp_path / "cache.db")
    text = "same text"
    model = "model:test"

    cache.put(EmbeddingResult(text=text, embedding=[1.0], model=model, dimension=1))
    cache.put(EmbeddingResult(text=text, embedding=[2.0], model=model, dimension=1))

    assert cache.get(text, model) == [2.0]


def test_cache_persists_across_instances(tmp_path):
    """Cache data survives closing and reopening."""
    from engram.embeddings.cache import EmbeddingCache
    from engram.embeddings.base import EmbeddingResult

    cache_path = tmp_path / "cache.db"
    embedding = [0.5, 0.6, 0.7]

    c1 = EmbeddingCache(cache_path)
    c1.put(EmbeddingResult(text="persist test", embedding=embedding, model="m:1", dimension=3))

    c2 = EmbeddingCache(cache_path)
    assert c2.get("persist test", "m:1") == embedding


def test_cache_stats(tmp_path):
    from engram.embeddings.cache import EmbeddingCache
    from engram.embeddings.base import EmbeddingResult

    cache = EmbeddingCache(tmp_path / "cache.db")
    cache.put(EmbeddingResult(text="a", embedding=[1.0], model="m:1", dimension=1))
    cache.put(EmbeddingResult(text="b", embedding=[2.0], model="m:1", dimension=1))
    cache.put(EmbeddingResult(text="c", embedding=[3.0], model="m:2", dimension=1))

    stats = cache.get_stats()
    assert stats["total_embeddings"] == 3
    assert stats["unique_models"] == 2


def test_cache_key_is_deterministic(tmp_path):
    """Same text+model always produces same cache key."""
    from engram.embeddings.cache import EmbeddingCache
    cache = EmbeddingCache(tmp_path / "cache.db")
    key1 = cache._make_key("hello", "model:x")
    key2 = cache._make_key("hello", "model:x")
    key3 = cache._make_key("hello", "model:y")
    assert key1 == key2
    assert key1 != key3


# ---------------------------------------------------------------------------
# CachedEmbedder tests
# ---------------------------------------------------------------------------

def test_cached_embedder_hit_prevents_underlying_call(tmp_path):
    """Cache hit should not call underlying embedder again."""
    from engram.embeddings.cache import EmbeddingCache, CachedEmbedder
    from tests.conftest import MockEmbedder

    call_count = 0
    original_embed = MockEmbedder.embed

    class CountingEmbedder(MockEmbedder):
        def embed(self, text):
            nonlocal call_count
            call_count += 1
            return super().embed(text)

    cache = EmbeddingCache(tmp_path / "cache.db")
    cached = CachedEmbedder(CountingEmbedder(), cache)

    # First call: miss
    r1 = cached.embed("test text")
    assert call_count == 1
    assert cached.misses == 1
    assert cached.hits == 0

    # Second call: hit
    r2 = cached.embed("test text")
    assert call_count == 1  # No additional call
    assert cached.hits == 1
    assert cached.misses == 1

    # Embeddings match
    assert r1.embedding == r2.embedding


def test_cached_embedder_batch_mixed(tmp_path):
    """Batch with some cached, some not."""
    from engram.embeddings.cache import EmbeddingCache, CachedEmbedder
    from engram.embeddings.base import EmbeddingResult
    from tests.conftest import MockEmbedder

    cache = EmbeddingCache(tmp_path / "cache.db")
    embedder = MockEmbedder()

    # Pre-cache "text_a"
    r = embedder.embed("text_a")
    cache.put(r)

    cached = CachedEmbedder(embedder, cache)
    result = cached.embed_batch(["text_a", "text_b", "text_c"])

    assert len(result.embeddings) == 3
    assert cached.hits == 1   # text_a was cached
    assert cached.misses == 2  # text_b, text_c were not


def test_cached_embedder_hit_count_accumulated(tmp_path):
    """Hit/miss counters accumulate across multiple calls."""
    from engram.embeddings.cache import EmbeddingCache, CachedEmbedder
    from tests.conftest import MockEmbedder

    cache = EmbeddingCache(tmp_path / "cache.db")
    cached = CachedEmbedder(MockEmbedder(), cache)

    texts = ["text_a", "text_b", "text_c"]

    # First pass: all misses
    for t in texts:
        cached.embed(t)
    assert cached.misses == 3
    assert cached.hits == 0

    # Second pass: all hits
    for t in texts:
        cached.embed(t)
    assert cached.hits == 3
    assert cached.misses == 3


def test_cached_embedder_dimension_passthrough(tmp_path):
    """CachedEmbedder passes through dimension from underlying embedder."""
    from engram.embeddings.cache import EmbeddingCache, CachedEmbedder
    from tests.conftest import MockEmbedder

    cache = EmbeddingCache(tmp_path / "cache.db")
    embedder = MockEmbedder()
    cached = CachedEmbedder(embedder, cache)

    assert cached.dimension == MockEmbedder.DIMENSION
    assert cached.model_name == embedder.model_name
