from __future__ import annotations

from dataclasses import replace
import json

import pytest

from rag_lib.interop import describe_rag_pipeline
from rag_lib.pipeline import RAGPipeline
from rag_lib.storage.base import StoredChunk


class _FakeRetriever:
    def retrieve_with_details(self, query: str, collection: str = "default"):
        chunk = StoredChunk(
            chunk_id="c1",
            text="dense text",
            context_text="dense text with context",
            score=0.9,
            source_id="doc.txt:0",
            doc_type="paper",
            metadata={
                "strategy": "fixed_size",
                "title": "Doc",
                "dense_rank": 1,
                "bm25_rank": 1,
                "retrieval_channels": ["dense", "bm25"],
            },
        )
        return {
            "dense_results": [chunk],
            "bm25_results": [chunk],
            "fused_results": [chunk],
            "diagnostics": {"dense_count": 1, "bm25_count": 1, "fused_count": 1},
        }

    def assemble_prompt_with_selection(
        self, query: str, chunks, max_context_tokens=None, system_prompt: str = ""
    ):
        prompt = f"{system_prompt}\n\nContext:\n{chunks[0].context_text}\n\nQuestion: {query}\n\nAnswer:".strip()
        return (
            prompt,
            list(chunks),
            {
                "selected_count": len(chunks),
                "budget": max_context_tokens,
                "selected_chunk_ids": [c.chunk_id for c in chunks],
            },
        )


class _ManyFakeRetriever(_FakeRetriever):
    def retrieve_with_details(self, query: str, collection: str = "default"):
        chunks = [
            StoredChunk(
                chunk_id=f"c{index}",
                text=f"dense text {index}",
                context_text=f"dense text {index} with context",
                score=0.9 - index / 10,
                source_id=f"doc.txt:{index}",
                doc_type="paper",
                metadata={
                    "strategy": "fixed_size",
                    "title": "Doc",
                    "dense_rank": index + 1,
                    "retrieval_channels": ["dense"],
                },
            )
            for index in range(4)
        ]
        return {
            "dense_results": chunks,
            "bm25_results": [],
            "fused_results": chunks,
            "diagnostics": {"dense_count": 4, "bm25_count": 0, "fused_count": 4},
        }


class _FakeReranker:
    def rerank(self, query: str, chunks, k: int = 5):
        return list(chunks)[:k]


class _FailingReranker:
    def rerank(self, query: str, chunks, k: int = 5):
        raise RuntimeError("fabricated reranker failure")


def _make_pipeline() -> RAGPipeline:
    pipeline = object.__new__(RAGPipeline)
    pipeline._config = {"retriever": {"n_candidates": 5, "n_results": 3, "max_context_tokens": 200}}
    pipeline._retriever = _FakeRetriever()
    pipeline._reranker = _FakeReranker()
    pipeline._expander = None
    return pipeline


def test_stored_chunk_to_retrieved_document_preserves_stage_and_rank():
    chunk = StoredChunk(
        chunk_id="c1",
        text="short",
        context_text="expanded",
        score=0.5,
        source_id="doc.txt:0",
        doc_type="paper",
        metadata={"section": "Intro"},
    )
    doc = chunk.to_retrieved_document(stage="dense", rank=2)
    assert doc.doc_id == "c1"
    assert doc.metadata["stage"] == "dense"
    assert doc.metadata["rank"] == 2
    assert doc.title == "Intro"


def test_describe_rag_pipeline_reports_interop_features():
    descriptor = describe_rag_pipeline(_make_pipeline())
    assert descriptor.provider == "rag_lib"
    assert "hybrid_retrieval" in descriptor.features
    assert descriptor.metadata["has_reranker"] is True


def test_inspect_query_emits_retrieval_trace_events_and_selected_results():
    pipeline = _make_pipeline()
    trace = pipeline.inspect_query(
        "test query", max_context_tokens=128, system_prompt="Be precise."
    )
    assert trace.query == "test query"
    assert len(trace.selected_results) == 1
    assert any(event.event_type == "retrieval_stage1_completed" for event in trace.events)
    assert any(event.event_type == "retrieval_reranked" for event in trace.events)
    assert any(event.event_type == "retrieval_prompt_assembled" for event in trace.events)
    payload = trace.to_serializable_dict()
    assert payload["selected_results"][0]["doc_id"] == "c1"
    assert payload["diagnostics"]["selected_count"] == 1


def test_retrieval_trace_operation_result_includes_evidence_flows():
    pipeline = _make_pipeline()
    trace = pipeline.inspect_query(
        "test query", max_context_tokens=128, system_prompt="Be precise."
    )
    result = trace.to_operation_result()
    flows = result.diagnostics.get("evidence_flows", [])
    assert flows
    flow = flows[0]
    assert flow["source"] == "rag"
    assert flow["stage"] == "selected"
    assert flow["provenance"]["doc_id"] == "c1"
    assert "prompt_assembly" in flow["transformations"]


def test_inspect_query_enforces_final_count_without_reranker():
    pipeline = _make_pipeline()
    pipeline._retriever = _ManyFakeRetriever()
    pipeline._config["retriever"]["n_results"] = 2
    pipeline._reranker = None

    trace = pipeline.inspect_query("test query")

    assert len(trace.fused_results) == 4
    assert len(trace.reranked_results) == 2
    assert len(trace.selected_results) == 2


def test_inspect_query_enforces_final_count_when_reranker_fails():
    pipeline = _make_pipeline()
    pipeline._retriever = _ManyFakeRetriever()
    pipeline._config["retriever"]["n_results"] = 1
    pipeline._reranker = _FailingReranker()

    trace = pipeline.inspect_query("test query")

    assert len(trace.reranked_results) == 1


def test_identifier_projection_excludes_text_prompt_and_source_paths():
    pipeline = _make_pipeline()
    trace = pipeline.inspect_query(
        "private manuscript question", system_prompt="private system text"
    )

    projection = trace.to_identifier_projection(
        entry_id_by_source={"doc.txt": "entry-1"},
        allowed_entry_ids={"entry-1"},
    )
    serialized = json.dumps(projection)

    assert projection["projection_schema_version"] == "2"
    assert projection["retrieved"][0]["entry_id"] == "entry-1"
    assert projection["retrieved"][0]["fused_score"] == "0.9"
    assert projection["retrieved"][0]["chunk_digest"].startswith("sha256:")
    assert projection["channel_execution"] == {
        "dense": {
            "attempted": True,
            "status": "completed",
            "result_count": 1,
            "diagnostic_codes": [],
        },
        "bm25": {
            "attempted": True,
            "status": "completed",
            "result_count": 1,
            "diagnostic_codes": [],
        },
    }
    assert "private manuscript question" not in serialized
    assert "private system text" not in serialized
    assert "dense text" not in serialized
    assert "doc.txt" not in serialized


def test_identifier_projection_rejects_unmapped_source():
    trace = _make_pipeline().inspect_query("query")

    with pytest.raises(ValueError, match="No corpus entry id"):
        trace.to_identifier_projection(entry_id_by_source={}, allowed_entry_ids={"entry-1"})


def test_identifier_projection_rejects_truncated_context():
    trace = _make_pipeline().inspect_query("query")
    trace.reranked_results[0].metadata["context_truncated"] = True

    with pytest.raises(ValueError, match="truncated model-visible context"):
        trace.to_identifier_projection(
            entry_id_by_source={"doc.txt": "entry-1"},
            allowed_entry_ids={"entry-1"},
        )


@pytest.mark.parametrize(
    ("entry_id", "chunk_id", "message"),
    [
        ("/private/entry", "c1", "unsafe identifiers"),
        ("entry-1", "/private/chunk", "unsafe chunk id"),
    ],
)
def test_identifier_projection_rejects_path_like_identifiers(entry_id, chunk_id, message):
    trace = _make_pipeline().inspect_query("query")
    trace = replace(
        trace,
        reranked_results=(replace(trace.reranked_results[0], doc_id=chunk_id),),
    )

    with pytest.raises(ValueError, match=message):
        trace.to_identifier_projection(
            entry_id_by_source={"doc.txt": entry_id},
            allowed_entry_ids={entry_id},
        )


def test_identifier_projection_rejects_entry_outside_exact_allowlist():
    trace = _make_pipeline().inspect_query("query")

    with pytest.raises(ValueError, match="outside the allowed set"):
        trace.to_identifier_projection(
            entry_id_by_source={"doc.txt": "entry-2"},
            allowed_entry_ids={"entry-1"},
        )


def test_identifier_projection_rejects_channel_without_rank():
    trace = _make_pipeline().inspect_query("query")
    trace.reranked_results[0].metadata["dense_rank"] = None

    with pytest.raises(ValueError, match="inconsistent dense rank"):
        trace.to_identifier_projection(
            entry_id_by_source={"doc.txt": "entry-1"},
            allowed_entry_ids={"entry-1"},
        )


def test_identifier_projection_retains_bm25_degradation_status():
    pipeline = _make_pipeline()
    trace = pipeline.inspect_query("query")
    stage_event = next(
        event for event in trace.events if event.event_type == "retrieval_stage1_completed"
    )
    stage_event.payload["warnings"] = ["bm25_search_failed"]
    stage_event.payload["bm25_count"] = 0

    projection = trace.to_identifier_projection(
        entry_id_by_source={"doc.txt": "entry-1"},
        allowed_entry_ids={"entry-1"},
    )

    assert projection["channel_execution"]["bm25"] == {
        "attempted": True,
        "status": "degraded",
        "result_count": 0,
        "diagnostic_codes": ["bm25_search_failed"],
    }
