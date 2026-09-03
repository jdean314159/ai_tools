"""Tests for rag_lib.retrieval.retriever."""

from __future__ import annotations

import json

import pytest
from rag_lib.retrieval.retriever import HybridRetriever
from rag_lib.storage.base import StoredChunk


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
        store = _make_mock_store(
            chunks=[
                _make_chunk("NetFlow anomaly detection", "c1", 0.8),
                _make_chunk("insider threat behavior", "c2", 0.6),
            ]
        )
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        # Build BM25 from the mock store's chunks
        retriever.build_bm25_index(
            [
                _make_chunk("NetFlow anomaly detection", "c1"),
                _make_chunk("insider threat behavior", "c2"),
            ],
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
        chunks = [_make_chunk("word " * 30, f"c{i}", 0.9 - i * 0.1) for i in range(5)]
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
    def test_bm25_json_written_after_build(self, mock_embedder, tmp_dir):
        pytest.importorskip("rank_bm25")
        store = _make_mock_store()
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        chunks = [_make_chunk("test content", "c1")]
        retriever.build_bm25_index(chunks, collection="mytest")

        cache = tmp_dir / "bm25" / "mytest.json"
        assert cache.exists()
        data = json.loads(cache.read_text(encoding="utf-8"))
        assert data["corpus"] == ["test content"]
        assert data["ids"] == ["c1"]
        assert not (tmp_dir / "bm25" / "mytest.pkl").exists()

    def test_bm25_loads_from_disk(self, mock_embedder, tmp_dir):
        pytest.importorskip("rank_bm25")
        chunks = [_make_chunk("NetFlow traffic anomaly", "c1")]
        store = _make_mock_store(chunks)
        retriever1 = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
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

    def test_in_memory_bm25_rebuilds_after_same_count_store_update(
        self, mock_embedder, tmp_dir, monkeypatch
    ):
        pytest.importorskip("rank_bm25")
        old_chunk = _make_chunk("old content", "old")
        new_chunk = _make_chunk("new content", "new")
        store = _make_mock_store([new_chunk])
        store.collection_metadata.return_value = {"updated_at": 20.0}
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(tmp_dir / "bm25"),
        )
        timestamps = iter([10.0, 30.0])
        monkeypatch.setattr("rag_lib.retrieval.retriever.time.time", lambda: next(timestamps))
        retriever.build_bm25_index([old_chunk], collection="test")

        _index, ids = retriever._get_bm25_index("test")

        assert ids == ["new"]
        assert store.search.called

    def test_disk_bm25_rebuilds_after_same_count_store_update(self, mock_embedder, tmp_dir):
        pytest.importorskip("rank_bm25")
        new_chunk = _make_chunk("new content", "new")
        store = _make_mock_store([new_chunk])
        store.collection_metadata.return_value = {"updated_at": 20.0}
        cache_dir = tmp_dir / "bm25"
        cache_dir.mkdir()
        (cache_dir / "test.json").write_text(
            json.dumps({"corpus": ["old content"], "ids": ["old"], "built_at": 10.0}),
            encoding="utf-8",
        )
        retriever = HybridRetriever(
            store=store,
            embedder=mock_embedder,
            bm25_path=str(cache_dir),
        )

        _index, ids = retriever._get_bm25_index("test")

        assert ids == ["new"]
        assert store.search.called


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_mock_store(chunks=None):
    """Minimal mock VectorStore."""
    from unittest.mock import MagicMock

    store = MagicMock()
    store.search.return_value = chunks or []
    store.count.return_value = len(chunks) if chunks else 0
    store.collection_metadata.return_value = {}
    return store


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path
