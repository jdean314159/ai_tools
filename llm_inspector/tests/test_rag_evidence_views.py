from __future__ import annotations

from rag_lib.pipeline import RAGPipeline
from rag_lib.storage.base import StoredChunk
from llm_inspector.rag import RAGInspector


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


class _FakeReranker:
    def rerank(self, query: str, chunks, k: int = 5):
        return list(chunks)[:k]


class _FakeGeneratorPipeline(RAGPipeline):
    pass


def _make_pipeline() -> RAGPipeline:
    pipeline = object.__new__(RAGPipeline)
    pipeline._config = {"retriever": {"n_candidates": 5, "n_results": 3, "max_context_tokens": 200}}
    pipeline._retriever = _FakeRetriever()
    pipeline._reranker = _FakeReranker()
    pipeline._expander = None
    return pipeline


def test_rag_inspector_prints_evidence_flow(capsys):
    inspector = RAGInspector()
    inspector.add_pipeline("RAG", _make_pipeline())
    results = inspector.query_all("test query")
    inspector.print_comparison(results)
    out = capsys.readouterr().out
    assert "Evidence flow:" in out
    assert "provenance={" in out
    assert "xforms=" in out
