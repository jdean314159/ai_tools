"""Regression test for engram's public API surface.

Verifies that every name in engram.__all__ resolves and that the documented
standalone memory API remains exported from the package root.
"""
import engram


def test_all_public_names_resolve():
    """Every name in __all__ must be accessible on the engram module."""
    missing = [name for name in engram.__all__ if not hasattr(engram, name)]
    assert not missing, f"engram.__all__ names that failed to resolve: {missing}"


def test_expected_public_names_are_exported():
    """Core standalone engram APIs must remain package-root exports."""
    expected = {
        "ProjectMemory",
        "ProjectType",
        "TokenBudget",
        "Telemetry",
        "TelemetryEvent",
        "AugmentRequest",
        "AugmentResult",
        "PromptAugmenter",
        "OllamaEmbedder",
        "EmbeddingService",
    }
    assert expected <= set(engram.__all__)
