"""
tests/test_rag_inspector.py

RAGInspector and adapter tests. No live Engram or ChromaDB required.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from llm_engines.contracts import Chunk
from llm_inspector.rag import RAGInspector, EngramRAGAdapter, ChromaDBRAGAdapter
from llm_engines.backends.mock import MockEngine


# ---------------------------------------------------------------------------
# Minimal in-process RAGPipeline for testing
# ---------------------------------------------------------------------------


class FixedPipeline:
    """Always returns the same chunks and response."""

    def __init__(self, name: str, chunks: list[Chunk], response: str = "Fixed response"):
        self.name = name
        self._chunks = chunks
        self._response = response

    def retrieve(self, query: str) -> list[Chunk]:
        return self._chunks

    def assemble_prompt(self, query: str, chunks: list[Chunk]) -> str:
        ctx = "\n".join(c.content for c in chunks)
        return f"{ctx}\n\nQ: {query}"

    def generate(self, prompt: str) -> str:
        return self._response


class FailingPipeline:
    """Always fails on retrieve."""

    def retrieve(self, query: str) -> list[Chunk]:
        raise RuntimeError("deliberate failure")

    def assemble_prompt(self, query: str, chunks: list[Chunk]) -> str:
        return query

    def generate(self, prompt: str) -> str:
        return ""


# ---------------------------------------------------------------------------
# RAGInspector tests
# ---------------------------------------------------------------------------


class TestRAGInspector:
    def test_no_pipelines_raises(self) -> None:
        inspector = RAGInspector()
        with pytest.raises(ValueError, match="No pipelines"):
            inspector.query_all("test query")

    def test_single_pipeline_returns_result(self) -> None:
        inspector = RAGInspector()
        chunks = [Chunk(content="Paris is the capital of France.", source_id="1", score=0.9)]
        inspector.add_pipeline("fixed", FixedPipeline("fixed", chunks))
        results = inspector.query_all("What is the capital of France?")
        assert len(results) == 1
        assert results[0].pipeline_name == "fixed"
        assert len(results[0].chunks) == 1
        assert results[0].error is None
        assert results[0].response == "Fixed response"

    def test_failing_pipeline_captured_as_error(self) -> None:
        inspector = RAGInspector()
        inspector.add_pipeline("failing", FailingPipeline())
        results = inspector.query_all("test")
        assert results[0].error is not None
        assert "deliberate failure" in results[0].error
        assert results[0].chunks == []

    def test_multiple_pipelines(self) -> None:
        inspector = RAGInspector()
        c1 = [Chunk(content="Result A", source_id="a1", score=0.9)]
        c2 = [
            Chunk(content="Result B", source_id="b1", score=0.8),
            Chunk(content="Result C", source_id="b2", score=0.7),
        ]
        inspector.add_pipeline("Pipeline A", FixedPipeline("A", c1))
        inspector.add_pipeline("Pipeline B", FixedPipeline("B", c2))
        results = inspector.query_all("query")
        assert len(results) == 2
        assert results[0].pipeline_name == "Pipeline A"
        assert results[1].pipeline_name == "Pipeline B"
        assert len(results[1].chunks) == 2

    def test_latency_is_populated(self) -> None:
        inspector = RAGInspector()
        inspector.add_pipeline("t", FixedPipeline("t", []))
        results = inspector.query_all("q")
        assert results[0].latency_ms >= 0.0

    def test_compare_pipelines_returns_dict(self) -> None:
        inspector = RAGInspector()
        inspector.add_pipeline("p", FixedPipeline("p", []))
        all_results = inspector.compare_pipelines(["q1", "q2"], print_results=False)
        assert "q1" in all_results
        assert "q2" in all_results
        assert len(all_results["q1"]) == 1

    def test_print_comparison_no_crash(self, capsys) -> None:
        inspector = RAGInspector()
        chunks = [Chunk(content="Some context text", source_id="1", score=0.85)]
        inspector.add_pipeline("test", FixedPipeline("test", chunks, "A test response"))
        results = inspector.query_all("What happened?")
        inspector.print_comparison(results)
        out = capsys.readouterr().out
        assert "test" in out
        assert "Some context text" in out


# ---------------------------------------------------------------------------
# EngramRAGAdapter tests
# ---------------------------------------------------------------------------


class TestEngramRAGAdapter:
    def test_fallback_to_query_episodic(self) -> None:
        """Test the query_episodic fallback path."""
        from types import SimpleNamespace

        fake_ep = SimpleNamespace(id="1", text="Engram stored this fact.", importance=0.8)
        memory = MagicMock()
        del memory.retrieve  # force fallback path
        memory.query_episodic.return_value = [fake_ep]

        adapter = EngramRAGAdapter(memory, engine=MockEngine(), max_results=5)
        chunks = adapter.retrieve("test query")
        assert len(chunks) == 1
        assert chunks[0].content == "Engram stored this fact."
        assert chunks[0].score == 0.8

    def test_assemble_prompt_with_chunks(self) -> None:
        memory = MagicMock()
        adapter = EngramRAGAdapter(memory, engine=MockEngine())
        chunks = [
            Chunk(content="Paris is in France.", source_id="1", score=0.9),
            Chunk(content="France is in Europe.", source_id="2", score=0.8),
        ]
        prompt = adapter.assemble_prompt("Where is Paris?", chunks)
        assert "Paris is in France" in prompt
        assert "France is in Europe" in prompt
        assert "Where is Paris?" in prompt

    def test_generate_uses_engine(self) -> None:
        memory = MagicMock()
        engine = MockEngine(response_fn=lambda r: "Generated answer")
        adapter = EngramRAGAdapter(memory, engine=engine)
        result = adapter.generate("some prompt")
        assert result == "Generated answer"

    def test_retrieve_failure_returns_empty(self) -> None:
        memory = MagicMock()
        memory.query_episodic.side_effect = RuntimeError("DB error")
        del memory.retrieve
        adapter = EngramRAGAdapter(memory, engine=MockEngine())
        chunks = adapter.retrieve("query")
        assert chunks == []


# ---------------------------------------------------------------------------
# ChromaDBRAGAdapter tests
# ---------------------------------------------------------------------------


class TestChromaDBRAGAdapter:
    def _fake_collection(self):
        """Returns a mock ChromaDB collection."""
        collection = MagicMock()
        collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["Doc one text", "Doc two text"]],
            "distances": [[0.1, 0.3]],
            "metadatas": [[{"source": "a"}, {"source": "b"}]],
        }
        return collection

    def test_retrieve_converts_to_chunks(self) -> None:
        collection = self._fake_collection()
        adapter = ChromaDBRAGAdapter(collection, engine=MockEngine())
        chunks = adapter.retrieve("test query")
        assert len(chunks) == 2
        assert chunks[0].content == "Doc one text"
        assert chunks[0].score == pytest.approx(0.9, abs=0.01)  # 1 - 0.1
        assert chunks[1].score == pytest.approx(0.7, abs=0.01)  # 1 - 0.3

    def test_retrieve_failure_returns_empty(self) -> None:
        collection = MagicMock()
        collection.query.side_effect = Exception("ChromaDB error")
        adapter = ChromaDBRAGAdapter(collection, engine=MockEngine())
        chunks = adapter.retrieve("query")
        assert chunks == []

    def test_generate_uses_engine(self) -> None:
        collection = self._fake_collection()
        engine = MockEngine(response_fn=lambda r: "Chroma response")
        adapter = ChromaDBRAGAdapter(collection, engine=engine)
        result = adapter.generate("prompt")
        assert result == "Chroma response"
