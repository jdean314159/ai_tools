"""Regression tests for package public API surfaces.

For each package that declares ``__all__``, every listed name must resolve as
an attribute on the imported module.
"""
import importlib

import engram
import pytest


PACKAGES = [
    "llm_harness_core",
    "llm_engines",
    "reasoning_loop_guard",
    "action_trajectory_loop_guard",
    "engram",
    "rag_lib",
    "llm_inspector",
    "llm_inspector_ui",
    "agent_lib",
    "mail_lib",
]


@pytest.mark.parametrize(
    "package_name",
    PACKAGES,
    ids=[f"package-{index}" for index in range(len(PACKAGES))],
)
def test_all_exports_resolve(package_name: str) -> None:
    module = importlib.import_module(package_name)
    declared = getattr(module, "__all__", None)
    if declared is None:
        pytest.skip(f"{package_name} declares no __all__")

    missing = [name for name in declared if not hasattr(module, name)]
    assert not missing, f"{package_name}.__all__ names that failed to resolve: {missing}"


def test_expected_engram_public_names_are_exported() -> None:
    """Core standalone engram APIs must remain package-root exports."""
    expected = {
        "ProjectMemory",
        "ProjectType",
        "TokenBudget",
        "Telemetry",
        "TelemetryEvent",
        "AugmentRequest",
        "AugmentResult",
        "MemoryLayer",
        "MemoryObservation",
        "PromptAugmenter",
        "PromptHint",
        "RecallContribution",
        "RecallQuery",
        "OllamaEmbedder",
        "EmbeddingService",
    }
    assert expected <= set(engram.__all__)
