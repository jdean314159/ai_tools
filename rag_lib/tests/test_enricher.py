"""Tests for rag_lib.ingestion.enricher."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from rag_lib.ingestion.enricher import ContextualEnricher
from rag_lib.ingestion.chunker import TextChunk


def _make_chunk(text: str, idx: int = 0) -> TextChunk:
    return TextChunk(
        text=text,
        context_text=text + " [context]",
        source_id=f"doc.txt:{idx}",
        doc_type="thesis",
        chunk_index=idx,
        metadata={"file_hash": "abc123"},
    )


class TestTextChunkEmbedText:
    def test_embed_text_defaults_to_text(self):
        """embed_text defaults to text if not explicitly set."""
        chunk = _make_chunk("hello world")
        assert chunk.embed_text == "hello world"

    def test_embed_text_can_be_set_separately(self):
        """embed_text can be set to enriched version independently."""
        chunk = _make_chunk("hello world")
        chunk.embed_text = "This is context. hello world"
        assert chunk.text == "hello world"
        assert chunk.embed_text == "This is context. hello world"
        assert chunk.context_text == "hello world [context]"

    def test_three_fields_are_independent(self):
        """All three text roles are independent."""
        chunk = TextChunk(
            text="short sentence.",
            context_text="surrounding paragraph text",
            embed_text="document context description. short sentence.",
            source_id="doc:0",
            doc_type="paper",
            chunk_index=0,
        )
        assert chunk.text != chunk.context_text
        assert chunk.text != chunk.embed_text
        assert chunk.context_text != chunk.embed_text


class TestContextualEnricher:
    def test_ollama_provider_init(self):
        enricher = ContextualEnricher(provider="ollama", model="qwen3:8b")
        assert enricher._provider == "ollama"
        assert enricher._model == "qwen3:8b"

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown enricher provider"):
            ContextualEnricher(provider="invalid")

    def test_cloud_provider_requires_api_key(self):
        """Cloud providers raise if API key env var is not set."""
        import os
        env_key = "TEST_MISSING_KEY_XYZ"
        if env_key in os.environ:
            del os.environ[env_key]
        with pytest.raises(ValueError, match=env_key):
            ContextualEnricher(
                provider="anthropic",
                model="claude-haiku-4-5",
                api_key_env=env_key,
            )

    def test_enrich_sets_embed_text(self):
        """Successful enrichment sets embed_text on chunks."""
        enricher = ContextualEnricher(provider="ollama")
        enricher._generate = MagicMock(return_value="This is a test description")

        chunks = [_make_chunk("NetFlow data was collected over five weeks.")]
        enricher.enrich(chunks, doc_title="dissertation.pdf",
                        doc_type="thesis", doc_intro="Abstract text here")

        assert chunks[0].embed_text == \
            "This is a test description. NetFlow data was collected over five weeks."
        assert chunks[0].text == "NetFlow data was collected over five weeks."

    def test_enrich_falls_back_on_failure(self):
        """Failed generation leaves embed_text equal to text."""
        enricher = ContextualEnricher(provider="ollama")
        enricher._generate = MagicMock(return_value="")

        chunks = [_make_chunk("original text")]
        enricher.enrich(chunks)
        assert chunks[0].embed_text == "original text"

    def test_enrich_empty_list(self):
        enricher = ContextualEnricher(provider="ollama")
        result = enricher.enrich([])
        assert result == []

    def test_cache_hit_skips_generate(self):
        """Second enrich call on same chunk skips LLM call."""
        enricher = ContextualEnricher(provider="ollama", cache=True)
        enricher._generate = MagicMock(return_value="Cached description")

        chunk = _make_chunk("test content", idx=0)
        chunk.metadata["file_hash"] = "hash1"

        enricher.enrich([chunk], file_hash="hash1")
        assert enricher._generate.call_count == 1

        # Second call — same chunk_id
        chunk2 = _make_chunk("test content", idx=0)
        chunk2.metadata["file_hash"] = "hash1"
        enricher.enrich([chunk2], file_hash="hash1")
        # Should NOT call generate again
        assert enricher._generate.call_count == 1
        assert chunk2.embed_text.startswith("Cached description")

    def test_cache_disabled_always_calls_generate(self):
        enricher = ContextualEnricher(provider="ollama", cache=False)
        enricher._generate = MagicMock(return_value="description")

        chunk = _make_chunk("text", idx=0)
        enricher.enrich([chunk], file_hash="hash1")
        enricher.enrich([chunk], file_hash="hash1")
        assert enricher._generate.call_count == 2

    def test_embed_text_exceeding_max_tokens_falls_back(self):
        """embed_text that would exceed max_embed_tokens falls back to text."""
        enricher = ContextualEnricher(provider="ollama", max_embed_tokens=5)
        enricher._generate = MagicMock(return_value="A very long description")

        chunk = _make_chunk("word " * 10)  # 10 words + description = > 5
        enricher.enrich([chunk], file_hash="hash1")
        # Should fall back to plain text
        assert chunk.embed_text == chunk.text

    def test_clean_strips_label_prefixes(self):
        enricher = ContextualEnricher(provider="ollama")
        assert enricher._clean("Description: test sentence") == "test sentence"
        assert enricher._clean("Context: test sentence") == "test sentence"
        assert enricher._clean("  test sentence  ") == "test sentence"

    def test_clean_takes_first_line(self):
        enricher = ContextualEnricher(provider="ollama")
        result = enricher._clean("First line\nSecond line\nThird line")
        assert result == "First line"

    def test_build_embed_text(self):
        enricher = ContextualEnricher(provider="ollama")
        result = enricher._build_embed_text(
            "This is about NetFlow.", "Raw chunk content here."
        )
        assert result == "This is about NetFlow. Raw chunk content here."

    def test_ollama_connection_error_returns_empty(self):
        """Connection refused should return empty string, not raise."""
        enricher = ContextualEnricher(
            provider="ollama",
            host="http://localhost:19999",  # nothing listening here
            timeout=1,
        )
        result = enricher._generate("test prompt")
        assert result == ""

    def test_clear_cache(self):
        enricher = ContextualEnricher(provider="ollama", cache=True)
        enricher._cache_store["key"] = "value"
        assert enricher.cache_size == 1
        enricher.clear_cache()
        assert enricher.cache_size == 0
