"""
tests/test_openai_backend.py

OpenAIEngine offline unit tests. All HTTP is mocked — no API key, no network.

Live tests: pytest -m openai  (requires OPENAI_API_KEY)
"""
from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("openai")

from llm_engines.contracts import (
    ChatMessage,
    EmbeddingRequest,
    GenerationRequest,
    GenerationResponse,
    EmbeddingResponse,
    ToolCall,
    ToolParameterSchema,
    ToolSpec,
    StreamFinishedEvent,
    TextDeltaEvent,
    ToolCallEvent,
    LogprobModel,
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
                    timeout="300",
                )
                assert eng.is_cloud is False
                assert MockSync.call_args.kwargs["api_key"] == "dummy"
                assert MockSync.call_args.kwargs["timeout"] == 300.0

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

    @pytest.mark.parametrize("thinking", [True, False])
    def test_local_compat_passes_thinking_preference(self, engine, thinking) -> None:
        engine.is_cloud = False
        engine._client.chat.completions.create.return_value = _fake_completion()
        engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content="Analyze")],
            thinking=thinking,
        ))
        kwargs = engine._client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": thinking}
        }

    def test_cloud_openai_does_not_receive_local_thinking_option(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content="Analyze")],
            thinking=True,
        ))
        kwargs = engine._client.chat.completions.create.call_args.kwargs
        assert "extra_body" not in kwargs

    def test_json_schema_is_forwarded_as_strict_response_format(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion(
            '{"answer": 42}'
        )
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "integer"}},
            "required": ["answer"],
            "additionalProperties": False,
        }

        engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content="Return the answer")],
            json_schema=schema,
        ))

        kwargs = engine._client.chat.completions.create.call_args.kwargs
        assert kwargs["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": "llm_engines_response",
                "schema": schema,
                "strict": True,
            },
        }

    def test_capabilities(self, engine) -> None:
        caps = engine.get_capabilities()
        assert caps.chat is True
        assert caps.tool_calling is True
        assert caps.embeddings is True
        assert caps.async_streaming is True
        assert caps.logprobs is True
        assert caps.vision is False

    def test_local_capabilities_disable_embeddings_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("openai.OpenAI"), patch("openai.AsyncOpenAI"):
                from llm_engines.backends.openai import OpenAIEngine

                local = OpenAIEngine(model="local", is_cloud=False)

        assert local.get_capabilities().embeddings is False

    def test_local_embeddings_can_be_enabled_explicitly(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("openai.OpenAI"), patch("openai.AsyncOpenAI"):
                from llm_engines.backends.openai import OpenAIEngine

                local = OpenAIEngine(
                    model="local", is_cloud=False, supports_embeddings=True
                )

        assert local.get_capabilities().embeddings is True
        assert isinstance(local, LogprobModel)


class TestOpenAITools:

    def test_replayed_tool_arguments_are_json_not_python_repr(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        request = GenerationRequest(messages=[
            ChatMessage(
                role="assistant",
                tool_calls=[ToolCall(
                    call_id="call-1",
                    name="add",
                    arguments={"a": 28, "b": 37, "label": "it's valid"},
                )],
            ),
            ChatMessage(role="tool", tool_call_id="call-1", content="65"),
        ])
        spec = ToolSpec(
            name="add",
            description="Add two integers",
            parameters={
                "a": ToolParameterSchema(type="integer", description="first"),
                "b": ToolParameterSchema(type="integer", description="second"),
            },
            required_params=["a", "b"],
        )

        engine.generate_with_tools(request, [spec])

        messages = engine._client.chat.completions.create.call_args.kwargs["messages"]
        encoded = messages[0]["tool_calls"][0]["function"]["arguments"]
        assert json.loads(encoded) == {"a": 28, "b": 37, "label": "it's valid"}
        assert "'a'" not in encoded

    def test_tool_response_is_parsed_for_replay(self, engine) -> None:
        raw_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="add", arguments='{"a":28,"b":37}'),
        )
        raw = SimpleNamespace(
            id="chatcmpl_tool",
            model="local-model",
            choices=[_fake_choice(None, "tool_calls", [raw_call])],
            usage=_fake_usage(),
        )
        engine._client.chat.completions.create.return_value = raw

        response = engine.generate_with_tools(
            _req("Add 28 and 37"),
            [ToolSpec(name="add", description="Add", parameters={})],
        )

        assert response.finish_reason == "tool_call"
        assert response.message.tool_calls == [ToolCall(
            call_id="call-1",
            name="add",
            arguments={"a": 28, "b": 37},
        )]


class _AsyncChunks:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def iterate():
            for chunk in self._chunks:
                yield chunk
        return iterate()


def _stream_chunk(*, content=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tool_delta(index, *, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class TestOpenAIToolStreaming:

    @staticmethod
    def _collect(engine, request, tools):
        async def collect():
            return [event async for event in engine.stream_with_tools_async(request, tools)]
        return asyncio.run(collect())

    def test_buffers_arguments_until_complete_json(self, engine) -> None:
        engine._async_client.chat.completions.create = AsyncMock(return_value=_AsyncChunks([
            _stream_chunk(tool_calls=[_tool_delta(
                0, call_id="call-1", name="add", arguments='{"a":'
            )]),
            _stream_chunk(tool_calls=[_tool_delta(
                0, arguments='28,"b":37}'
            )]),
            _stream_chunk(finish_reason="tool_calls"),
        ]))
        spec = ToolSpec(name="add", description="Add", parameters={})

        events = self._collect(engine, _req("Add"), [spec])

        assert events == [
            ToolCallEvent(tool_call=ToolCall(
                call_id="call-1", name="add", arguments={"a": 28, "b": 37}
            )),
            StreamFinishedEvent(finish_reason="tool_call"),
        ]

    def test_emits_text_deltas_and_terminal_event(self, engine) -> None:
        engine._async_client.chat.completions.create = AsyncMock(return_value=_AsyncChunks([
            _stream_chunk(content="Hello"),
            _stream_chunk(content=" world"),
            _stream_chunk(finish_reason="stop"),
        ]))

        events = self._collect(engine, _req("Hello"), [])

        assert events == [
            TextDeltaEvent(text="Hello"),
            TextDeltaEvent(text=" world"),
            StreamFinishedEvent(finish_reason="stop"),
        ]

    def test_rejects_incomplete_tool_arguments(self, engine) -> None:
        from llm_engines.contracts import GenerationError

        engine._async_client.chat.completions.create = AsyncMock(return_value=_AsyncChunks([
            _stream_chunk(tool_calls=[_tool_delta(
                0, call_id="call-1", name="add", arguments='{"a":'
            )]),
            _stream_chunk(finish_reason="tool_calls"),
        ]))

        with pytest.raises(GenerationError, match="Invalid streamed tool arguments"):
            self._collect(
                engine,
                _req("Add"),
                [ToolSpec(name="add", description="Add", parameters={})],
            )


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

    def test_disabled_local_embeddings_fail_before_provider_call(self) -> None:
        from llm_engines.backends.openai import OpenAIEngine
        from llm_engines.contracts import GenerationError

        with patch.dict(os.environ, {}, clear=True):
            with patch("openai.OpenAI") as sync, patch("openai.AsyncOpenAI"):
                local = OpenAIEngine(model="local", is_cloud=False)
                with pytest.raises(GenerationError, match="Embeddings are disabled"):
                    local.embed(EmbeddingRequest(texts=["test"]))
                sync.return_value.embeddings.create.assert_not_called()


class TestOpenAILogprobs:

    def test_parses_provider_token_logprobs(self, engine) -> None:
        items = [
            SimpleNamespace(token="LOG", logprob=-0.1, bytes=[76, 79, 71]),
            SimpleNamespace(token="PROB", logprob=-0.2, bytes=None),
        ]
        choice = _fake_choice("LOGPROB", "stop")
        choice.logprobs = SimpleNamespace(content=items)
        engine._client.chat.completions.create.return_value = SimpleNamespace(
            id="chatcmpl-logprob",
            model="local",
            choices=[choice],
            usage=_fake_usage(),
        )

        result = engine.generate_with_logprobs(_req("Return LOGPROB"), top_logprobs=2)

        assert result.text == "LOGPROB"
        assert [item.token for item in result.token_logprobs] == ["LOG", "PROB"]
        assert result.token_logprobs[0].logprob == -0.1
        kwargs = engine._client.chat.completions.create.call_args.kwargs
        assert kwargs["logprobs"] is True
        assert kwargs["top_logprobs"] == 2


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
