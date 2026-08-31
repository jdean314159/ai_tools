"""Tests for rag_lib.ingestion.chunker."""

from __future__ import annotations

import pytest
from rag_lib.ingestion.chunker import (
    Chunker,
    _sentences,
    _sentence_window,
    _fixed_size,
    _hierarchical,
    _semantic,
)
from rag_lib.ingestion.loader import LoadedDocument
from rag_lib.errors import ChunkerError


PROSE = (
    "The sky is blue. Water is wet. Fire is hot. Ice is cold. Wind blows. Snow falls. Rain drops."
)

LONG_TEXT = " ".join(f"Word{i}" for i in range(300))


# ------------------------------------------------------------------
# Sentence splitter
# ------------------------------------------------------------------


class TestSentenceSplitter:
    def test_basic_split(self):
        sents = _sentences("Hello world. How are you? Fine thanks.")
        assert len(sents) == 3

    def test_abbreviation_handling(self):
        """Abbreviations like Dr., e.g., Fig. should not split sentences."""
        sents = _sentences("Dr. Smith works at Acme Inc. He is great.")
        # At minimum should not produce 4+ fragments
        assert len(sents) <= 3

    def test_decimal_numbers(self):
        sents = _sentences("Version 2.4.1 was released. It fixes bugs.")
        assert len(sents) >= 1  # should not crash

    def test_empty_input(self):
        assert _sentences("") == []

    def test_single_sentence(self):
        sents = _sentences("Just one sentence here.")
        assert len(sents) == 1
        assert sents[0] == "Just one sentence here."


# ------------------------------------------------------------------
# Sentence window strategy
# ------------------------------------------------------------------


class TestSentenceWindow:
    def test_chunk_count(self):
        chunks = _sentence_window(PROSE, "f.txt", "policy", window_size=2)
        sents = _sentences(PROSE)
        assert len(chunks) == len(sents)

    def test_d7_invariant(self):
        """context_text must be >= text (window expansion)."""
        chunks = _sentence_window(PROSE, "f.txt", "policy", window_size=2)
        for c in chunks:
            assert len(c.context_text) >= len(c.text), (
                f"D7 violated: context_text shorter than text for chunk {c.chunk_index}"
            )

    def test_center_chunk_has_window(self):
        chunks = _sentence_window(PROSE, "f.txt", "policy", window_size=2)
        # Middle chunk should have neighbors in context
        mid = chunks[len(chunks) // 2]
        assert len(mid.context_text.split()) > len(mid.text.split())

    def test_boundary_chunks(self):
        """First and last chunks should still have context (one-sided window)."""
        chunks = _sentence_window(PROSE, "f.txt", "policy", window_size=2)
        assert chunks[0].context_text != ""
        assert chunks[-1].context_text != ""

    def test_source_id_format(self):
        chunks = _sentence_window(PROSE, "doc.txt", "policy", window_size=1)
        for i, c in enumerate(chunks):
            assert c.source_id == f"doc.txt:{i}"

    def test_metadata_strategy(self):
        chunks = _sentence_window(PROSE, "f.txt", "policy", window_size=1)
        assert all(c.metadata["strategy"] == "sentence_window" for c in chunks)

    def test_empty_text_returns_empty(self):
        assert _sentence_window("", "f.txt", "policy") == []


# ------------------------------------------------------------------
# Fixed-size strategy
# ------------------------------------------------------------------


class TestFixedSize:
    def test_d7_text_equals_context(self):
        """For fixed-size, text == context_text."""
        chunks = _fixed_size(LONG_TEXT, "f.txt", "spec", chunk_size=50, chunk_overlap=5)
        for c in chunks:
            assert c.text == c.context_text

    def test_overlap_produces_shared_words(self):
        words = ["word"] * 100
        text = " ".join(words)
        chunks = _fixed_size(text, "f.txt", "spec", chunk_size=20, chunk_overlap=5)
        assert len(chunks) > 1
        # Adjacent chunks should share words due to overlap
        c1_words = set(chunks[0].text.split())
        c2_words = set(chunks[1].text.split())
        assert len(c1_words & c2_words) > 0

    def test_chunk_size_approximately_respected(self):
        chunks = _fixed_size(LONG_TEXT, "f.txt", "spec", chunk_size=30, chunk_overlap=5)
        for c in chunks:
            assert len(c.text.split()) <= 35  # allow small overshoot

    def test_empty_text(self):
        assert _fixed_size("", "f.txt", "spec") == []


# ------------------------------------------------------------------
# Hierarchical strategy
# ------------------------------------------------------------------


class TestHierarchical:
    def test_d7_context_larger_than_text(self):
        """Leaf text is small; context_text is the parent section."""
        chunks = _hierarchical(LONG_TEXT, "f.txt", "spec", chunk_sizes=[100, 40, 15])
        assert len(chunks) > 0
        # At least some chunks should have larger context than text
        expanded = [c for c in chunks if len(c.context_text.split()) > len(c.text.split())]
        assert len(expanded) > 0, "No hierarchical chunk has expanded context"

    def test_leaf_size_bounded(self):
        chunks = _hierarchical(LONG_TEXT, "f.txt", "spec", chunk_sizes=[100, 40, 15])
        for c in chunks:
            assert len(c.text.split()) <= 20  # leaf_size + small buffer

    def test_single_level_fallback(self):
        """Single-element chunk_sizes falls back to fixed-size behavior."""
        chunks = _hierarchical(LONG_TEXT, "f.txt", "spec", chunk_sizes=[50])
        assert len(chunks) > 0

    def test_produces_multiple_chunks(self):
        chunks = _hierarchical(LONG_TEXT, "f.txt", "spec", chunk_sizes=[100, 40, 15])
        assert len(chunks) > 5

    def test_metadata_strategy(self):
        chunks = _hierarchical(LONG_TEXT, "f.txt", "spec", chunk_sizes=[100, 40, 15])
        assert all(c.metadata["strategy"] == "hierarchical" for c in chunks)


# ------------------------------------------------------------------
# Semantic strategy
# ------------------------------------------------------------------


class TestSemantic:
    def test_fallback_without_embedder(self):
        """Without embedder, should fall back to sentence_window."""
        chunks = _semantic(PROSE, "f.txt", "mixed", embedder=None)
        assert len(chunks) > 0
        # Fallback: should produce sentence-level chunks
        assert all(c.metadata.get("strategy") in ("sentence_window", "semantic") for c in chunks)

    def test_max_sentences_fallback(self, mocker):
        """Exceeding max_sentences triggers sentence_window fallback."""
        long_text = ". ".join([f"Sentence {i}" for i in range(600)]) + "."
        chunks = _semantic(long_text, "f.txt", "mixed", max_sentences=100, embedder=None)
        assert len(chunks) > 0

    def test_with_mock_embedder(self, mock_embedder):
        """With embedder, should produce chunks at topic boundaries."""
        chunks = _semantic(
            PROSE,
            "f.txt",
            "mixed",
            embedder=mock_embedder,
            breakpoint_percentile=50,
        )
        assert len(chunks) >= 1


# ------------------------------------------------------------------
# Chunker class (routing + D7 enforcement)
# ------------------------------------------------------------------


class TestChunker:
    def test_routes_policy_to_sentence_window(self, sample_config):
        chunker = Chunker(config=sample_config)
        doc = LoadedDocument(PROSE, [], "f.txt", "policy", "abc", {})
        chunks = chunker.chunk(doc)
        assert all(c.metadata["strategy"] == "sentence_window" for c in chunks)

    def test_routes_spec_to_hierarchical(self, sample_config):
        chunker = Chunker(config=sample_config)
        doc = LoadedDocument(LONG_TEXT, [], "f.txt", "spec", "abc", {})
        chunks = chunker.chunk(doc)
        assert all(c.metadata["strategy"] == "hierarchical" for c in chunks)

    def test_routes_unknown_to_fixed_size(self, sample_config):
        chunker = Chunker(config=sample_config)
        doc = LoadedDocument(LONG_TEXT, [], "f.txt", "unknown_type", "abc", {})
        chunks = chunker.chunk(doc)
        assert all(c.metadata["strategy"] == "fixed_size" for c in chunks)

    def test_token_limit_raises_chunker_error(self, sample_config):
        """Chunks exceeding max_embed_tokens raise ChunkerError (D7)."""
        chunker = Chunker(config=sample_config, max_embed_tokens=5)
        doc = LoadedDocument("word " * 50, [], "f.txt", "policy", "abc", {})
        with pytest.raises(ChunkerError, match="max_embed_tokens"):
            chunker.chunk(doc)

    def test_empty_doc_raises_chunker_error(self, sample_config):
        chunker = Chunker(config=sample_config)
        doc = LoadedDocument("   ", [], "f.txt", "policy", "abc", {})
        with pytest.raises(ChunkerError, match="Empty document"):
            chunker.chunk(doc)

    def test_chunk_id_is_deterministic(self, sample_config):
        chunker = Chunker(config=sample_config)
        doc = LoadedDocument(PROSE, [], "f.txt", "policy", "deadbeef", {})
        chunks1 = chunker.chunk(doc)
        chunks2 = chunker.chunk(doc)
        ids1 = [c.chunk_id("deadbeef") for c in chunks1]
        ids2 = [c.chunk_id("deadbeef") for c in chunks2]
        assert ids1 == ids2
