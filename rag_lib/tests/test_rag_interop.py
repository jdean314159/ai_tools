from __future__ import annotations

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
            metadata={"strategy": "fixed_size", "title": "Doc"},
        )
        return {
            "dense_results": [chunk],
            "bm25_results": [chunk],
            "fused_results": [chunk],
            "diagnostics": {"dense_count": 1, "bm25_count": 1, "fused_count": 1},
        }

    def assemble_prompt_with_selection(self, query: str, chunks, max_context_tokens=None, system_prompt: str = ""):
        prompt = f"{system_prompt}\n\nContext:\n{chunks[0].context_text}\n\nQuestion: {query}\n\nAnswer:".strip()
        return prompt, list(chunks), {"selected_count": len(chunks), "budget": max_context_tokens, "selected_chunk_ids": [c.chunk_id for c in chunks]}


class _FakeReranker:
    def rerank(self, query: str, chunks, k: int = 5):
        return list(chunks)[:k]


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
    trace = pipeline.inspect_query("test query", max_context_tokens=128, system_prompt="Be precise.")
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
    trace = pipeline.inspect_query("test query", max_context_tokens=128, system_prompt="Be precise.")
    result = trace.to_operation_result()
    flows = result.diagnostics.get("evidence_flows", [])
    assert flows
    flow = flows[0]
    assert flow["source"] == "rag"
    assert flow["stage"] == "selected"
    assert flow["provenance"]["doc_id"] == "c1"
    assert "prompt_assembly" in flow["transformations"]
