"""
tests/test_llm_adapter.py

EngramLLMAdapter tests using MockEngine. No live LLM or Engram required.
"""
from __future__ import annotations

import json
import pytest

from llm_engines.contracts import ChatMessage, GenerationRequest
from llm_engines.backends.mock import MockEngine
from engram.adapters.llm_adapter import EngramLLMAdapter, ExtractionResult


@pytest.fixture()
def adapter():
    return EngramLLMAdapter(MockEngine())


class TestEmbedding:

    def test_embedding_raises_without_embed_capability(self, adapter) -> None:
        """MockEngine declares embeddings=False — should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="does not support embeddings"):
            adapter.generate_embedding("test text")

    def test_embedding_with_dedicated_embed_model(self) -> None:
        """
        When a separate embed_model is provided, it should be used.
        Here we stub the embed call directly.
        """
        from llm_engines.contracts import EmbeddingResponse
        from unittest.mock import MagicMock, patch

        embed_engine = MagicMock()
        embed_engine.get_capabilities.return_value = MagicMock(embeddings=True)
        embed_engine.embed.return_value = EmbeddingResponse(
            vectors=[[0.1, 0.2, 0.3]],
            dimensions=3,
            model_name="nomic-embed-text",
            backend="ollama",
        )

        adapter = EngramLLMAdapter(MockEngine(), embed_model=embed_engine)
        vec = adapter.generate_embedding("hello world")
        assert vec == [0.1, 0.2, 0.3]
        embed_engine.embed.assert_called_once()

    def test_batch_embedding(self) -> None:
        from llm_engines.contracts import EmbeddingResponse
        from unittest.mock import MagicMock

        embed_engine = MagicMock()
        embed_engine.get_capabilities.return_value = MagicMock(embeddings=True)
        embed_engine.embed.return_value = EmbeddingResponse(
            vectors=[[0.1, 0.2], [0.3, 0.4]],
            dimensions=2,
            model_name="nomic-embed-text",
            backend="ollama",
        )

        adapter = EngramLLMAdapter(MockEngine(), embed_model=embed_engine)
        vecs = adapter.generate_embeddings_batch(["text a", "text b"])
        assert len(vecs) == 2
        assert vecs[0] == [0.1, 0.2]


class TestEntityExtraction:

    def test_valid_json_response_parsed(self) -> None:
        payload = json.dumps({
            "entities": [{"type": "Person", "name": "Alice"}],
            "relationships": [{"subject": "Alice", "predicate": "WORKS_ON", "object": "auth"}],
        })
        engine = MockEngine(response_fn=lambda r: payload)
        adapter = EngramLLMAdapter(engine)
        result = adapter.extract_entities("Alice works on auth module")
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "Alice"
        assert len(result["relationships"]) == 1

    def test_markdown_fenced_json_parsed(self) -> None:
        payload = '```json\n{"entities": [{"type": "Person", "name": "Bob"}], "relationships": []}\n```'
        engine = MockEngine(response_fn=lambda r: payload)
        adapter = EngramLLMAdapter(engine)
        result = adapter.extract_entities("Bob is here")
        assert result["entities"][0]["name"] == "Bob"

    def test_bad_json_returns_empty_result(self) -> None:
        engine = MockEngine(response_fn=lambda r: "not json at all")
        adapter = EngramLLMAdapter(engine)
        result = adapter.extract_entities("some text")
        assert result == {"entities": [], "relationships": []}

    def test_generation_failure_returns_empty_result(self) -> None:
        from llm_engines.contracts import GenerationError

        def fail(r):
            raise GenerationError("deliberate failure")

        engine = MockEngine(response_fn=fail)
        adapter = EngramLLMAdapter(engine)
        result = adapter.extract_entities("some text")
        assert result == {"entities": [], "relationships": []}

    def test_temperature_zero_for_extraction(self) -> None:
        """Extraction must use temperature=0 for determinism."""
        captured = {}

        def capture(request):
            captured["temperature"] = request.temperature
            return '{"entities": [], "relationships": []}'

        engine = MockEngine(response_fn=capture)
        adapter = EngramLLMAdapter(engine)
        adapter.extract_entities("test")
        assert captured["temperature"] == 0.0


class TestGenerate:

    def test_returns_string(self, adapter) -> None:
        result = adapter.generate("Summarise this text")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_system_prompt_included(self) -> None:
        captured = {}

        def capture(request):
            captured["messages"] = request.messages
            return "response"

        engine = MockEngine(response_fn=capture)
        adapter = EngramLLMAdapter(engine)
        adapter.generate("hello", system="You are a summariser")
        roles = [m.role for m in captured["messages"]]
        assert roles[0] == "system"
        assert captured["messages"][0].content == "You are a summariser"
