"""
engram_lite public API contract test  (ADR-007, migration step 1).

This test FREEZES the engram_lite public surface so that the facade
migration (replacing local implementation with re-exports / a shim over
engram) cannot silently change what students and downstream users import.

If a change to this test is required, it must be a deliberate, reviewed
change to the public contract -- not an accident of the migration.

Covers:
  1. The exact set of names exported via __all__.
  2. Every exported name is importable and not None.
  3. The public method names + parameter names of ProjectMemory.
  4. Import-time behavior: importing engram_lite must not import torch.
"""
from __future__ import annotations

import importlib
import inspect
import sys

import pytest

import engram_lite


# ---------------------------------------------------------------------------
# 1. Frozen __all__ snapshot
# ---------------------------------------------------------------------------

EXPECTED_ALL = {
    "__version__",
    # Core
    "AugmentRequest", "AugmentResult", "PromptAugmenter",
    "ProjectMemory",
    "describe_memory", "trace_to_memory_records",
    "augment_result_to_interop_result",
    # Embeddings
    "Embedder", "EmbeddingResult", "BatchEmbeddingResult",
    "OllamaEmbedder", "EmbeddingService",
    "EmbeddingCache", "CachedEmbedder",
    # Storage
    "ChromaDBStore", "DimensionMismatchError", "SchemaManager",
    # Semantic
    "SemanticGraph",
    "SemanticExtractor", "ExtractedFact", "ExtractionResult",
    "ForgettingConfig", "ForgettingPolicy",
    "detect_contradiction",
    # Telemetry
    "Telemetry", "TelemetryEvent", "log_sink", "json_file_sink",
}


def test_all_matches_frozen_snapshot():
    """__all__ must equal the frozen contract exactly -- no additions or removals."""
    actual = set(engram_lite.__all__)
    missing = EXPECTED_ALL - actual
    added = actual - EXPECTED_ALL
    assert not missing, f"public API removed names: {sorted(missing)}"
    assert not added, f"public API added names without contract update: {sorted(added)}"


def test_every_exported_name_resolves():
    """Every name in __all__ must be a real, non-None attribute."""
    for name in EXPECTED_ALL:
        assert hasattr(engram_lite, name), f"{name} missing from engram_lite"
        assert getattr(engram_lite, name) is not None, f"{name} resolved to None"


# ---------------------------------------------------------------------------
# 2. ProjectMemory public method contract
# ---------------------------------------------------------------------------

# method name -> ordered tuple of accepted parameter names (excluding 'self').
# Keyword-only params are included; **kwargs is represented by the literal
# "**kwargs" sentinel and is not positionally checked.
EXPECTED_PM_METHODS = {
    "describe_component": (),
    "new_session": ("session_id",),
    "get_recent_turns": ("session_id", "limit"),
    "add_turn": ("role", "text", "session_id"),
    "add_turns_batch": ("turns", "session_id"),
    "store_episodes_batch": ("episodes",),
    "store_episode": ("text", "metadata", "importance", "bypass_filter", "bypass_dedup"),
    "search_episodes": (
        "query", "n", "min_importance", "days_back",
        "min_relevance", "vector_similarity_threshold",
    ),
    "get_facts": ("query", "fact_type", "subject", "include_superseded", "limit"),
    "get_paired_exchanges": ("query", "n"),
    "reconcile_chromadb": (),
    "build_prompt": (
        "user_message", "query", "max_prompt_tokens", "reserve_output_tokens",
        "include_cold_fallback", "store_overflow_summary", "return_trace",
    ),
    "build_prompt_trace": ("user_message",),
    "build_interop_events": ("user_message",),
    "augment": ("request",),
    "delete_episode": ("episode_id",),
    "forget_session": ("session_id",),
    "forget_user_data": (),
    "index_text": ("text",),
    "run_lifecycle_maintenance": (),
    "get_stats": (),
    "close": (),
}


def _param_names(method) -> set[str]:
    sig = inspect.signature(method)
    return {
        name for name, p in sig.parameters.items()
        if name != "self" and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    }


@pytest.mark.parametrize("method_name", sorted(EXPECTED_PM_METHODS))
def test_project_memory_has_public_method(method_name):
    """Each contracted public method must exist and be callable."""
    pm = engram_lite.ProjectMemory
    assert hasattr(pm, method_name), f"ProjectMemory.{method_name} missing"
    assert callable(getattr(pm, method_name))


@pytest.mark.parametrize("method_name,expected_params", sorted(EXPECTED_PM_METHODS.items()))
def test_project_memory_method_accepts_contracted_params(method_name, expected_params):
    """
    Each contracted parameter name must still be accepted.

    This guards against signature drift during the shim migration (e.g.
    renaming `session_id` -> none, or `limit` -> `n`). A shim is permitted
    to ACCEPT extra params, but must not DROP a contracted one.
    """
    method = getattr(engram_lite.ProjectMemory, method_name)
    sig = inspect.signature(method)
    accepts_kwargs = any(
        p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
    )
    present = _param_names(method)
    for param in expected_params:
        # **kwargs can absorb any contracted keyword param, so only fail when
        # the param is genuinely absent AND there is no **kwargs catch-all.
        assert param in present or accepts_kwargs, (
            f"ProjectMemory.{method_name} dropped contracted param '{param}'"
        )


def test_no_unexpected_public_methods():
    """
    ProjectMemory must not GROW its public surface without a contract update.

    Lite invariants (ADR-007) are partly enforced by keeping the lite surface
    from quietly acquiring engram's advanced methods (respond, synthesize_now,
    audit_memory, get_context, etc.).
    """
    pm = engram_lite.ProjectMemory
    public = {
        name for name in dir(pm)
        if not name.startswith("_") and callable(getattr(pm, name))
    }
    # Exclude inherited object/dataclass noise that is not part of the API.
    public -= {"mro"}
    unexpected = public - set(EXPECTED_PM_METHODS)
    assert not unexpected, (
        f"ProjectMemory grew unexpected public methods: {sorted(unexpected)}. "
        f"If intentional, update EXPECTED_PM_METHODS and the ADR-007 contract."
    )


# ---------------------------------------------------------------------------
# 3. Import-time behavior
# ---------------------------------------------------------------------------

def test_importing_engram_lite_does_not_import_torch():
    """
    The lite surface must stay torch-free. ADR-007 keeps the RTRL/neural
    layer out of the lite public API; importing engram_lite must not pull
    PyTorch even transitively through engram.
    """
    # Drop any prior import so the assertion reflects engram_lite alone.
    for mod in list(sys.modules):
        if mod == "torch" or mod.startswith("torch."):
            del sys.modules[mod]
    importlib.reload(engram_lite)
    assert "torch" not in sys.modules, (
        "importing engram_lite pulled torch -- a lite-surface dependency leak"
    )
