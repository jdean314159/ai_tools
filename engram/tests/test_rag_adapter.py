"""
tests/test_rag_adapter.py

Offline unit tests for EngramRAGAdapter.

No Ollama, no SQLite, no filesystem — pure mock of ContextResult.
Tests cover:
  - RetrievalTrace structure and field mapping
  - per-layer document conversion (semantic, episodic, cold)
  - TraceEvent emission
  - assembled prompt format
  - empty-result edge cases
  - describe_component()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fake ContextResult and Episode (mirrors engram.project_memory internals)
# ---------------------------------------------------------------------------

@dataclass
class _FakeEpisode:
    id: str
    text: str
    timestamp: float = 1700000000.0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class _FakeContextResult:
    episodic: List[_FakeEpisode] = field(default_factory=list)
    semantic: List[Dict[str, Any]] = field(default_factory=list)
    cold: List[Dict[str, Any]] = field(default_factory=list)
    working: List[Any] = field(default_factory=list)
    episodic_tokens: int = 0
    semantic_tokens: int = 0
    cold_tokens: int = 0
    working_tokens: int = 0
    neural_meta: Optional[Dict[str, Any]] = None

    @property
    def total_tokens(self) -> int:
        return (
            self.episodic_tokens
            + self.semantic_tokens
            + self.cold_tokens
            + self.working_tokens
        )


def _fake_memory(ctx: _FakeContextResult) -> MagicMock:
    """Create a mock ProjectMemory that returns a fixed ContextResult."""
    pm = MagicMock()
    pm.project_id = "test_project"
    pm.get_context.return_value = ctx
    return pm


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def populated_ctx() -> _FakeContextResult:
    return _FakeContextResult(
        semantic=[
            {"type": "fact", "text": "Python uses GIL for thread safety.", "match_score": 0.91},
            {"type": "preference", "canonical_content": "User prefers async patterns.", "match_score": 0.75},
        ],
        episodic=[
            _FakeEpisode(id="ep_001", text="We decided to use SQLite.", timestamp=1700000001.0),
            _FakeEpisode(id="ep_002", text="Switched from Kuzu to SQLite in v0.2.", timestamp=1700000002.0),
        ],
        cold=[
            {"text": "Old architecture note: used Kuzu graph DB.", "score": 0.42},
        ],
        semantic_tokens=80,
        episodic_tokens=60,
        cold_tokens=20,
    )


@pytest.fixture()
def adapter(populated_ctx):
    from engram.adapters.rag_adapter import EngramRAGAdapter
    pm = _fake_memory(populated_ctx)
    return EngramRAGAdapter(pm, max_tokens=2048, episodic_n=5, semantic_n=5, cold_n=5)


@pytest.fixture()
def trace(adapter):
    return adapter.inspect_query("What database do we use?")


# ---------------------------------------------------------------------------
# RetrievalTrace structural tests
# ---------------------------------------------------------------------------

class TestRetrievalTraceStructure:

    def test_returns_retrieval_trace(self, trace):
        from rag_lib.interop import RetrievalTrace
        assert isinstance(trace, RetrievalTrace)

    def test_query_preserved(self, trace):
        assert trace.query == "What database do we use?"

    def test_collection_default(self, trace):
        assert trace.collection == "engram"

    def test_collection_custom(self, populated_ctx):
        from engram.adapters.rag_adapter import EngramRAGAdapter
        pm = _fake_memory(populated_ctx)
        adapter = EngramRAGAdapter(pm)
        t = adapter.inspect_query("q", collection="myproject")
        assert t.collection == "myproject"

    def test_query_variants_contains_query(self, trace):
        assert trace.query == trace.query_variants[0]

    def test_assembled_prompt_contains_query(self, trace):
        assert "What database do we use?" in trace.assembled_prompt

    def test_assembled_prompt_contains_memory_context(self, trace):
        assert "## Retrieved memory context" in trace.assembled_prompt

    def test_diagnostics_source_is_engram(self, trace):
        assert trace.diagnostics.get("source") == "engram"

    def test_diagnostics_token_counts(self, trace):
        assert trace.diagnostics["semantic_count"] == 2
        assert trace.diagnostics["episodic_count"] == 2
        assert trace.diagnostics["cold_count"] == 1
        assert trace.diagnostics["selected_count"] == 5  # 2+2+1


# ---------------------------------------------------------------------------
# Layer mapping tests
# ---------------------------------------------------------------------------

class TestLayerMapping:

    def test_dense_results_are_semantic(self, trace):
        """semantic layer maps to dense_results slot."""
        assert len(trace.dense_results) == 2
        for doc in trace.dense_results:
            assert doc.metadata.get("layer") == "semantic"
            assert doc.source == "engram:semantic"

    def test_bm25_results_are_episodic(self, trace):
        """episodic layer maps to bm25_results slot."""
        assert len(trace.bm25_results) == 2
        for doc in trace.bm25_results:
            assert doc.metadata.get("layer") == "episodic"
            assert doc.source == "engram:episodic"

    def test_fused_results_are_cold(self, trace):
        """cold layer maps to fused_results slot."""
        assert len(trace.fused_results) == 1
        assert trace.fused_results[0].source == "engram:cold"
        assert trace.fused_results[0].metadata.get("layer") == "cold"

    def test_selected_results_contain_all_layers(self, trace):
        """selected_results = semantic + episodic + cold combined."""
        assert len(trace.selected_results) == 5

    def test_selected_results_have_combined_rank(self, trace):
        ranks = [doc.metadata.get("combined_rank") for doc in trace.selected_results]
        assert ranks == list(range(1, 6))

    def test_reranked_results_empty(self, trace):
        """Engram reranks internally; we don't expose a separate reranked slot."""
        assert trace.reranked_results == ()


# ---------------------------------------------------------------------------
# Document content tests
# ---------------------------------------------------------------------------

class TestDocumentContent:

    def test_semantic_text_extracted_from_text_key(self, trace):
        texts = [d.text for d in trace.dense_results]
        assert "Python uses GIL for thread safety." in texts

    def test_semantic_text_extracted_from_canonical_content(self, trace):
        texts = [d.text for d in trace.dense_results]
        assert "User prefers async patterns." in texts

    def test_semantic_score_preserved(self, trace):
        scores = [d.score for d in trace.dense_results]
        assert 0.91 in scores
        assert 0.75 in scores

    def test_semantic_memory_type_in_metadata(self, trace):
        types = {d.metadata.get("memory_type") for d in trace.dense_results}
        assert "fact" in types
        assert "preference" in types

    def test_episodic_text_preserved(self, trace):
        texts = [d.text for d in trace.bm25_results]
        assert "We decided to use SQLite." in texts
        assert "Switched from Kuzu to SQLite in v0.2." in texts

    def test_episodic_doc_id_is_episode_id(self, trace):
        ids = {d.doc_id for d in trace.bm25_results}
        assert "ep_001" in ids
        assert "ep_002" in ids

    def test_episodic_timestamp_in_metadata(self, trace):
        ts_values = {d.metadata.get("timestamp") for d in trace.bm25_results}
        assert 1700000001.0 in ts_values

    def test_cold_text_extracted(self, trace):
        assert trace.fused_results[0].text == "Old architecture note: used Kuzu graph DB."

    def test_cold_score_extracted(self, trace):
        assert trace.fused_results[0].score == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# TraceEvent tests
# ---------------------------------------------------------------------------

class TestTraceEvents:

    def test_events_non_empty(self, trace):
        assert len(trace.events) > 0

    def test_semantic_event_present(self, trace):
        types = {e.event_type for e in trace.events}
        assert "engram_semantic_retrieved" in types

    def test_episodic_event_present(self, trace):
        types = {e.event_type for e in trace.events}
        assert "engram_episodic_retrieved" in types

    def test_cold_event_present_when_cold_results_exist(self, trace):
        types = {e.event_type for e in trace.events}
        assert "engram_cold_retrieved" in types

    def test_prompt_assembled_event_present(self, trace):
        types = {e.event_type for e in trace.events}
        assert "engram_prompt_assembled" in types

    def test_events_source_package(self, trace):
        assert all(e.source_package == "engram" for e in trace.events)

    def test_semantic_event_payload_count(self, trace):
        sem_event = next(e for e in trace.events if e.event_type == "engram_semantic_retrieved")
        assert sem_event.payload["count"] == 2

    def test_prompt_event_layer_breakdown(self, trace):
        pe = next(e for e in trace.events if e.event_type == "engram_prompt_assembled")
        layers = pe.payload["layers"]
        assert layers["semantic"] == 2
        assert layers["episodic"] == 2
        assert layers["cold"] == 1


# ---------------------------------------------------------------------------
# Empty result edge cases
# ---------------------------------------------------------------------------

class TestEmptyResults:

    @pytest.fixture()
    def empty_adapter(self):
        from engram.adapters.rag_adapter import EngramRAGAdapter
        pm = _fake_memory(_FakeContextResult())
        return EngramRAGAdapter(pm)

    def test_empty_returns_retrieval_trace(self, empty_adapter):
        from rag_lib.interop import RetrievalTrace
        trace = empty_adapter.inspect_query("anything")
        assert isinstance(trace, RetrievalTrace)

    def test_empty_selected_results(self, empty_adapter):
        trace = empty_adapter.inspect_query("anything")
        assert trace.selected_results == ()

    def test_empty_no_cold_event(self, empty_adapter):
        trace = empty_adapter.inspect_query("anything")
        types = {e.event_type for e in trace.events}
        assert "engram_cold_retrieved" not in types

    def test_empty_prompt_still_has_query(self, empty_adapter):
        trace = empty_adapter.inspect_query("no results")
        assert "no results" in trace.assembled_prompt


# ---------------------------------------------------------------------------
# retrieve() and assemble_prompt()
# ---------------------------------------------------------------------------

class TestRetrieveAndAssemble:

    def test_retrieve_returns_list(self, adapter):
        docs = adapter.retrieve("query")
        assert isinstance(docs, list)

    def test_retrieve_count_matches_selected(self, adapter, trace):
        docs = adapter.retrieve("What database do we use?")
        assert len(docs) == len(trace.selected_results)

    def test_assemble_prompt_includes_memory_header(self, adapter, trace):
        prompt = adapter.assemble_prompt("q", list(trace.selected_results))
        assert "## Retrieved memory context" in prompt

    def test_assemble_prompt_includes_query(self, adapter, trace):
        prompt = adapter.assemble_prompt("my question", list(trace.selected_results))
        assert "my question" in prompt

    def test_assemble_prompt_with_system_prompt(self, adapter, trace):
        prompt = adapter.assemble_prompt(
            "q", list(trace.selected_results), system_prompt="Be concise."
        )
        assert "Be concise." in prompt

    def test_assemble_prompt_empty_chunks(self, adapter):
        prompt = adapter.assemble_prompt("empty", [])
        assert "empty" in prompt

    def test_generate_returns_empty_string(self, adapter):
        assert adapter.generate("any prompt") == ""


# ---------------------------------------------------------------------------
# describe_component()
# ---------------------------------------------------------------------------

class TestDescribeComponent:

    def test_returns_capability_descriptor(self, adapter):
        from llm_harness_core import CapabilityDescriptor
        desc = adapter.describe_component()
        assert isinstance(desc, CapabilityDescriptor)

    def test_provider_is_engram(self, adapter):
        desc = adapter.describe_component()
        assert desc.provider == "engram"

    def test_features_include_multi_layer(self, adapter):
        desc = adapter.describe_component()
        assert "multi_layer" in desc.features

    def test_metadata_has_project_id(self, adapter):
        desc = adapter.describe_component()
        assert desc.metadata.get("project_id") == "test_project"


# ---------------------------------------------------------------------------
# get_context call verification
# ---------------------------------------------------------------------------

class TestGetContextCall:

    def test_get_context_called_with_query(self, populated_ctx):
        from engram.adapters.rag_adapter import EngramRAGAdapter
        pm = _fake_memory(populated_ctx)
        adapter = EngramRAGAdapter(pm, max_tokens=1024, episodic_n=3, semantic_n=4, cold_n=2)
        adapter.inspect_query("test query")
        call_kwargs = pm.get_context.call_args
        assert call_kwargs.kwargs["query"] == "test query"
        assert call_kwargs.kwargs["max_tokens"] == 1024
        assert call_kwargs.kwargs["episodic_n"] == 3
        assert call_kwargs.kwargs["semantic_n"] == 4
        assert call_kwargs.kwargs["cold_n"] == 2

    def test_max_context_tokens_overrides_default(self, populated_ctx):
        from engram.adapters.rag_adapter import EngramRAGAdapter
        pm = _fake_memory(populated_ctx)
        adapter = EngramRAGAdapter(pm, max_tokens=2048)
        adapter.inspect_query("q", max_context_tokens=512)
        call_kwargs = pm.get_context.call_args
        assert call_kwargs.kwargs["max_tokens"] == 512
