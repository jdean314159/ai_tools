"""
tests/test_openai_backend.py

OpenAIEngine offline unit tests. All HTTP is mocked — no API key, no network.

Live tests: pytest -m openai  (requires OPENAI_API_KEY)
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai")

from llm_engines.contracts import (
    ChatMessage,
    EmbeddingRequest,
    GenerationRequest,
    GenerationResponse,
    EmbeddingResponse,
)


# ---------------------------------------------------------------------------
# Fake OpenAI response builders
# ---------------------------------------------------------------------------

def _fake_usage(prompt=10, completion=20):
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


def _fake_choice(content="Hello!", finish_reason="stop", tool_calls=None):
    msg = SimpleNamespace(
        content=content,
        tool_calls=tool_calls or [],
        role="assistant",
    )
    return SimpleNamespace(message=msg, finish_reason=finish_reason)


def _fake_completion(content="Hello!", finish_reason="stop", model="gpt-4o-mini"):
    return SimpleNamespace(
        id="chatcmpl_123",
        model=model,
        choices=[_fake_choice(content, finish_reason)],
        usage=_fake_usage(),
    )


def _fake_embedding_response(vectors):
    items = [SimpleNamespace(embedding=v) for v in vectors]
    return SimpleNamespace(data=items)


@pytest.fixture()
def engine():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch("openai.OpenAI") as MockSync, \
             patch("openai.AsyncOpenAI") as MockAsync:
            MockSync.return_value = MagicMock()
            MockAsync.return_value = MagicMock()
            from llm_engines.backends.openai import OpenAIEngine
            eng = OpenAIEngine(model="gpt-4o-mini")
            eng._client = MockSync.return_value
            eng._async_client = MockAsync.return_value
            yield eng


def _req(content="Hello"):
    return GenerationRequest(messages=[ChatMessage(role="user", content=content)])


class TestOpenAIGenerate:

    def test_returns_generation_response(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        resp = engine.generate(_req())
        assert isinstance(resp, GenerationResponse)

    def test_content_and_role(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion("Test!")
        resp = engine.generate(_req())
        assert resp.message.content == "Test!"
        assert resp.message.role == "assistant"

    def test_finish_reason_stop(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion(
            finish_reason="stop"
        )
        resp = engine.generate(_req())
        assert resp.finish_reason == "stop"

    def test_finish_reason_length(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion(
            finish_reason="length"
        )
        resp = engine.generate(_req())
        assert resp.finish_reason == "length"

    def test_usage_populated(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        resp = engine.generate(_req())
        assert resp.usage.input_tokens == 10
        assert resp.usage.output_tokens == 20
        assert resp.usage.total_tokens == 30

    def test_model_name_from_response(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion(
            model="gpt-4o"
        )
        resp = engine.generate(_req())
        assert resp.model_name == "gpt-4o"

    def test_backend_is_openai(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        resp = engine.generate(_req())
        assert resp.backend == "openai"

    def test_empty_messages_raises(self, engine) -> None:
        from llm_engines.contracts import GenerationError
        with pytest.raises(GenerationError):
            engine.generate(GenerationRequest(messages=[]))

    def test_is_cloud_true_by_default(self, engine) -> None:
        assert engine.is_cloud is True

    def test_local_compat_does_not_require_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("openai.OpenAI") as MockSync, patch("openai.AsyncOpenAI") as MockAsync:
                from llm_engines.backends.openai import OpenAIEngine

                eng = OpenAIEngine(
                    model="local-model",
                    base_url="http://127.0.0.1:8080/v1",
                    is_cloud=False,
                    timeout=300,
                )

                assert eng.is_cloud is False
                kwargs = MockSync.call_args.kwargs
                assert kwargs["api_key"] == "dummy"
                assert kwargs["base_url"] == "http://127.0.0.1:8080/v1"

    def test_factory_local_compat_no_key(self) -> None:
        """EngineFactory.create('openai', is_cloud=False) must not require OPENAI_API_KEY."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("openai.OpenAI") as MockSync, patch("openai.AsyncOpenAI"):
                from llm_engines.factory import EngineFactory
                eng = EngineFactory.create(
                    "openai",
                    model="local-model",
                    base_url="http://127.0.0.1:8080/v1",
                    is_cloud=False,
                )
                assert eng.is_cloud is False
                assert MockSync.call_args.kwargs["api_key"] == "dummy"

    def test_is_cloud_false_for_local_compat(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            with patch("openai.OpenAI"), patch("openai.AsyncOpenAI"):
                from llm_engines.backends.openai import OpenAIEngine
                eng = OpenAIEngine(
                    model="local-model",
                    base_url="http://localhost:8000/v1",
                    is_cloud=False,
                )
        assert eng.is_cloud is False

    def test_cloud_mode_requires_api_key(self) -> None:
        from llm_engines.contracts import EngineConfigError

        with patch.dict(os.environ, {}, clear=True):
            with patch("openai.OpenAI"), patch("openai.AsyncOpenAI"):
                from llm_engines.backends.openai import OpenAIEngine
                with pytest.raises(EngineConfigError, match="OPENAI_API_KEY"):
                    OpenAIEngine(model="gpt-4o-mini", is_cloud=True)

    def test_stop_sequences_passed(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        request = GenerationRequest(
            messages=[ChatMessage(role="user", content="Hi")],
            stop=["<|end|>"],
        )
        engine.generate(request)
        kwargs = engine._client.chat.completions.create.call_args[1]
        assert kwargs["stop"] == ["<|end|>"]

    def test_capabilities(self, engine) -> None:
        caps = engine.get_capabilities()
        assert caps.chat is True
        assert caps.tool_calling is True
        assert caps.embeddings is True
        assert caps.async_streaming is True


class TestOpenAIEmbedding:

    def test_embed_returns_vectors(self, engine) -> None:
        engine._client.embeddings.create.return_value = _fake_embedding_response(
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        )
        resp = engine.embed(EmbeddingRequest(texts=["a", "b"]))
        assert isinstance(resp, EmbeddingResponse)
        assert len(resp.vectors) == 2
        assert resp.dimensions == 3
        assert resp.backend == "openai"

    def test_embed_uses_default_model(self, engine) -> None:
        engine._client.embeddings.create.return_value = _fake_embedding_response([[0.1]])
        engine.embed(EmbeddingRequest(texts=["test"]))
        kwargs = engine._client.embeddings.create.call_args[1]
        assert kwargs["model"] == "text-embedding-3-small"

    def test_embed_uses_request_model(self, engine) -> None:
        engine._client.embeddings.create.return_value = _fake_embedding_response([[0.1]])
        engine.embed(EmbeddingRequest(texts=["test"], model="text-embedding-3-large"))
        kwargs = engine._client.embeddings.create.call_args[1]
        assert kwargs["model"] == "text-embedding-3-large"


class TestOpenAIErrors:

    def test_rate_limit_error(self, engine) -> None:
        import openai
        from llm_engines.contracts import RateLimitError
        engine._client.chat.completions.create.side_effect = openai.RateLimitError(
            message="rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={},
        )
        with pytest.raises(RateLimitError):
            engine.generate(_req())

    def test_connection_error(self, engine) -> None:
        import openai
        from llm_engines.contracts import BackendUnavailableError
        engine._client.chat.completions.create.side_effect = (
            openai.APIConnectionError(request=MagicMock())
        )
        with pytest.raises(BackendUnavailableError):
            engine.generate(_req())

    def test_no_api_key_raises(self) -> None:
        from llm_engines.contracts import EngineConfigError
        with patch.dict(os.environ, {}, clear=True):
            with patch("openai.OpenAI"), patch("openai.AsyncOpenAI"):
                from llm_engines.backends.openai import OpenAIEngine
                with pytest.raises(EngineConfigError, match="OPENAI_API_KEY"):
                    OpenAIEngine(model="gpt-4o-mini", is_cloud=True)


@pytest.mark.openai
class TestOpenAILive:
    """Live tests — require OPENAI_API_KEY."""

    def test_generate_live(self) -> None:
        from llm_engines.backends.openai import OpenAIEngine
        engine = OpenAIEngine(model="gpt-4o-mini")
        resp = engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content="Reply with exactly: OK")],
            max_tokens=10,
            temperature=0.0,
        ))
        assert resp.message.content is not None
        assert resp.usage.total_tokens is not None

    def test_embed_live(self) -> None:
        from llm_engines.backends.openai import OpenAIEngine
        engine = OpenAIEngine(model="gpt-4o-mini")
        resp = engine.embed(EmbeddingRequest(texts=["Hello world"]))
        assert len(resp.vectors) == 1
        assert resp.dimensions > 0
