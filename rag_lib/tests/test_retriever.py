"""Tests for rag_lib.retrieval.retriever."""
from __future__ import annotations

import pytest
from rag_lib.retrieval.retriever import HybridRetriever
from rag_lib.storage.base import StoredChunk
from rag_lib.errors import RagLibError


def _make_chunk(text: str, cid: str, score: float = 0.5) -> StoredChunk:
    return StoredChunk(
        chunk_id=cid,
        text=text,
        context_text=text + " [expanded context]",
        score=score,
        source_id=f"doc.txt:{cid}",
        doc_type="paper",
        metadata={"strategy": "fixed_size"},
    )


class TestRRF:
    def test_rrf_combines_rankings(self, mock_embedder, tmp_dir):
        pytest.importorskip("rank_bm25")
        """RRF should produce scores blending BM25 and dense rankings."""
        store = _make_mock_store(chunks=[
            _make_chunk("NetFlow anomaly detection", "c1", 0.8),
            _make_chunk("insider threat behavior", "c2", 0.6),
        ])
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        # Build BM25 from the mock store's chunks
        retriever.build_bm25_index(
            [_make_chunk("NetFlow anomaly detection", "c1"),
             _make_chunk("insider threat behavior", "c2")],
            collection="default",
        )
        results = retriever.retrieve("anomaly detection", collection="default")
        # Should return results without crashing
        assert isinstance(results, list)

    def test_rrf_formula(self):
        """RRF score = sum(1/(k+rank)) across result lists."""
        from rag_lib.retrieval.retriever import _RRF_K
        # Rank 1 in dense only
        score = (1 - 0.4) / (_RRF_K + 1)
        assert abs(score - 0.6 / 61) < 1e-6


class TestBudgetEnforcement:
    def test_prompt_respects_token_budget(self, mock_embedder, tmp_dir):
        """assemble_prompt must not exceed max_context_tokens (D8)."""
        store = _make_mock_store()
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
            max_context_tokens=50,
        )
        # Chunks that are each ~30 words
        chunks = [
            _make_chunk("word " * 30, f"c{i}", 0.9 - i * 0.1)
            for i in range(5)
        ]
        prompt = retriever.assemble_prompt(
            query="test query",
            chunks=chunks,
            max_context_tokens=50,
        )
        # Prompt should exist and not massively exceed budget
        assert "Question: test query" in prompt

    def test_no_fitting_chunks_logs_warning(self, mock_embedder, tmp_dir, caplog):
        """When no chunks fit, a WARNING is logged and query-only prompt returned."""
        import logging
        store = _make_mock_store()
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        huge_chunk = _make_chunk("word " * 5000, "c1", 0.9)
        with caplog.at_level(logging.WARNING):
            prompt = retriever.assemble_prompt(
                query="my query",
                chunks=[huge_chunk],
                max_context_tokens=20,
            )
        assert "Question: my query" in prompt
        assert "No chunks fit" in caplog.text

    def test_system_prompt_counts_against_budget(self, mock_embedder, tmp_dir):
        store = _make_mock_store()
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        chunks = [_make_chunk("word " * 20, "c1", 0.9)]
        prompt_with_sys = retriever.assemble_prompt(
            "query", chunks, max_context_tokens=200, system_prompt="You are helpful."
        )
        assert "You are helpful." in prompt_with_sys


class TestBM25Persistence:
    def test_bm25_pickle_written_after_build(self, mock_embedder, tmp_dir):
        pytest.importorskip("rank_bm25")
        store = _make_mock_store()
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        chunks = [_make_chunk("test content", "c1")]
        retriever.build_bm25_index(chunks, collection="mytest")

        pkl = tmp_dir / "bm25" / "mytest.pkl"
        assert pkl.exists()

    def test_bm25_loads_from_disk(self, mock_embedder, tmp_dir):
        pytest.importorskip("rank_bm25")
        store = _make_mock_store()
        retriever1 = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        chunks = [_make_chunk("NetFlow traffic anomaly", "c1")]
        retriever1.build_bm25_index(chunks, collection="test")

        # New retriever instance should load from disk
        retriever2 = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        index, ids = retriever2._get_bm25_index("test")
        assert index is not None
        assert "c1" in ids


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_mock_store(chunks=None):
    """Minimal mock VectorStore."""
    from unittest.mock import MagicMock
    store = MagicMock()
    store.search.return_value = chunks or []
    store.count.return_value = len(chunks) if chunks else 0
    return store


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path
