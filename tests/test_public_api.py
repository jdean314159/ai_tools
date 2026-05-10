"""Regression test for engram's public API surface.

Verifies that every name in engram.__all__ resolves — including lazy
attributes loaded via __getattr__. This test would have caught the
engram.engine packaging failure that prompted the _LAZY_ATTRS refactor.
"""
import engram


def test_all_public_names_resolve():
    """Every name in __all__ must be accessible on the engram module."""
    missing = [name for name in engram.__all__ if not hasattr(engram, name)]
    assert not missing, f"engram.__all__ names that failed to resolve: {missing}"


def test_lazy_attrs_not_in_all_resolve():
    """Lazy attrs intentionally excluded from __all__ must still resolve."""
    extras = ["EpisodicMemory", "Episode", "SemanticMemory",
              "SurpriseFilter", "TITANSMemory", "NeuralMemory",
              "NeuralMemoryConfig", "engine"]
    missing = [name for name in extras if not hasattr(engram, name)]
    assert not missing, f"Lazy attrs that failed to resolve: {missing}"


def test_lazy_attrs_are_cached_after_first_access():
    """Second access must not call __getattr__ again (cached in globals)."""
    _ = engram.EmbeddingService   # trigger lazy load
    assert "EmbeddingService" in vars(engram), \
        "EmbeddingService should be cached in engram globals after first access"
