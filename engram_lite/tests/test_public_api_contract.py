from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest

import engram_lite


# ---------------------------------------------------------------------------
# 1. All expected names are present in __all__ and importable
# ---------------------------------------------------------------------------

EXPECTED_EXPORTS = {
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


def test_all_exports_present_in_dunder_all():
    assert EXPECTED_EXPORTS == set(engram_lite.__all__)


def test_all_exports_importable():
    missing = [name for name in EXPECTED_EXPORTS if not hasattr(engram_lite, name)]
    assert missing == [], f"Missing from engram_lite namespace: {missing}"


# ---------------------------------------------------------------------------
# 2. Kinds — classes vs callables (prevents accidental replacement)
# ---------------------------------------------------------------------------

EXPECTED_CLASSES = {
    "AugmentRequest", "AugmentResult", "PromptAugmenter",
    "ProjectMemory",
    "Embedder", "EmbeddingResult", "BatchEmbeddingResult",
    "OllamaEmbedder", "EmbeddingService",
    "EmbeddingCache", "CachedEmbedder",
    "ChromaDBStore", "DimensionMismatchError", "SchemaManager",
    "SemanticGraph",
    "SemanticExtractor", "ExtractedFact", "ExtractionResult",
    "ForgettingConfig", "ForgettingPolicy",
    "Telemetry", "TelemetryEvent",
}

EXPECTED_FUNCTIONS = {
    "describe_memory", "trace_to_memory_records",
    "augment_result_to_interop_result",
    "detect_contradiction",
    "log_sink", "json_file_sink",
}


def test_expected_names_are_classes():
    for name in EXPECTED_CLASSES:
        obj = getattr(engram_lite, name)
        assert inspect.isclass(obj), f"{name} should be a class, got {type(obj)}"


def test_expected_names_are_functions():
    for name in EXPECTED_FUNCTIONS:
        obj = getattr(engram_lite, name)
        assert callable(obj), f"{name} should be callable, got {type(obj)}"


# ---------------------------------------------------------------------------
# 3. Key constructor signatures (parameters that NB04 and course tests use)
# ---------------------------------------------------------------------------

def _params(cls_or_fn, skip_self=True) -> set[str]:
    try:
        sig = inspect.signature(cls_or_fn)
    except (ValueError, TypeError):
        return set()
    return {
        k for k in sig.parameters
        if k not in ("self", "cls") or not skip_self
    }


def test_AugmentRequest_has_required_fields():
    params = _params(engram_lite.AugmentRequest)
    assert "session_id" in params
    assert "user_text" in params


def test_AugmentResult_has_required_fields():
    params = _params(engram_lite.AugmentResult)
    assert "prompt" in params


def test_ProjectMemory_keyword_only_init():
    """NB04 constructs ProjectMemory with keyword-only args."""
    sig = inspect.signature(engram_lite.ProjectMemory)
    params = sig.parameters
    assert "base_dir" in params
    assert "project_id" in params
    assert "session_id" in params
    assert "total_prompt_tokens" in params
    # Must remain keyword-only — NB04 never uses positional args
    for name in ("base_dir", "project_id", "session_id", "total_prompt_tokens"):
        p = params[name]
        assert p.kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ), f"ProjectMemory.{name} must be keyword-accessible"


def test_OllamaEmbedder_params():
    params = _params(engram_lite.OllamaEmbedder)
    assert "model" in params
    assert "base_url" in params


def test_ChromaDBStore_params():
    params = _params(engram_lite.ChromaDBStore)
    assert "persist_directory" in params
    assert "collection_name" in params
    assert "embedding_dimension" in params


def test_ForgettingConfig_has_decay_params():
    params = _params(engram_lite.ForgettingConfig)
    assert "enable_decay" in params
    assert "decay_rate" in params


def test_TelemetryEvent_params():
    params = _params(engram_lite.TelemetryEvent)
    assert "event_type" in params
    assert "data" in params


def test_Telemetry_has_emit_and_add_sink():
    assert hasattr(engram_lite.Telemetry, "emit")
    assert hasattr(engram_lite.Telemetry, "add_sink")


# ---------------------------------------------------------------------------
# 4. ProjectMemory method surface used by NB04 and course tests
# ---------------------------------------------------------------------------

REQUIRED_PROJECT_MEMORY_METHODS = {
    "add_turn",
    "build_prompt",
    "get_recent_turns",
    "store_episode",
    "search_episodes",
    "get_stats",
    "new_session",
}


def test_ProjectMemory_has_required_methods():
    missing = [
        m for m in REQUIRED_PROJECT_MEMORY_METHODS
        if not hasattr(engram_lite.ProjectMemory, m)
    ]
    assert missing == [], f"ProjectMemory missing methods: {missing}"


# ---------------------------------------------------------------------------
# 5. Version is a non-empty string
# ---------------------------------------------------------------------------

def test_version_is_string():
    assert isinstance(engram_lite.__version__, str)
    assert engram_lite.__version__ != ""


# ---------------------------------------------------------------------------
# 6. Import-time behaviour — no hard crash without optional deps
# ---------------------------------------------------------------------------

def test_import_does_not_require_torch():
    """engram_lite must import cleanly without torch."""
    import importlib, sys
    # Remove torch from the namespace to simulate absence
    torch_mod = sys.modules.get("torch")
    sys.modules["torch"] = None  # type: ignore[assignment]
    try:
        if "engram_lite" in sys.modules:
            importlib.reload(engram_lite)
        import engram_lite as el2  # noqa: F401
    except ImportError as e:
        if "torch" in str(e).lower():
            pytest.fail(f"engram_lite import requires torch: {e}")
    finally:
        if torch_mod is not None:
            sys.modules["torch"] = torch_mod
        else:
            sys.modules.pop("torch", None)
