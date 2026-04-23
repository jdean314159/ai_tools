"""
tests/contract_tests/test_anthropic_engine.py

AnthropicEngine tests using a mocked client — no API key or network needed.
Live tests: pytest -m anthropic (requires ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("anthropic")

from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    ToolCall,
)


# ---------------------------------------------------------------------------
# Helpers: build a fake Anthropic response
# ---------------------------------------------------------------------------

def _fake_usage(input_tokens=10, output_tokens=20):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def _fake_text_block(text="Hello from Claude"):
    return SimpleNamespace(type="text", text=text)


def _fake_tool_block(id="call_1", name="get_weather", input=None):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input or {"city": "London"})


def _fake_response(content=None, stop_reason="end_turn", model="claude-sonnet-4-6"):
    return SimpleNamespace(
        id="msg_123",
        content=content or [_fake_text_block()],
        stop_reason=stop_reason,
        usage=_fake_usage(),
        model=model,
    )


@pytest.fixture()
def engine():
    """AnthropicEngine with mocked client."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic") as MockSync, \
             patch("anthropic.AsyncAnthropic") as MockAsync:
            MockSync.return_value = MagicMock()
            MockAsync.return_value = MagicMock()

            from llm_engines.backends.anthropic import AnthropicEngine
            eng = AnthropicEngine(model="claude-sonnet-4-6")
            eng._client = MockSync.return_value
            eng._async_client = MockAsync.return_value
            yield eng


def _req(content="Hello"):
    return GenerationRequest(messages=[ChatMessage(role="user", content=content)])


# ---------------------------------------------------------------------------
# ChatModel contract
# ---------------------------------------------------------------------------

class TestAnthropicChatModel:

    def test_returns_generation_response(self, engine) -> None:
        engine._client.messages.create.return_value = _fake_response()
        response = engine.generate(_req())
        assert isinstance(response, GenerationResponse)

    def test_message_role_is_assistant(self, engine) -> None:
        engine._client.messages.create.return_value = _fake_response()
        response = engine.generate(_req())
        assert response.message.role == "assistant"

    def test_content_populated(self, engine) -> None:
        engine._client.messages.create.return_value = _fake_response(
            content=[_fake_text_block("Test response")]
        )
        response = engine.generate(_req())
        assert response.message.content == "Test response"

    def test_finish_reason_stop(self, engine) -> None:
        engine._client.messages.create.return_value = _fake_response(stop_reason="end_turn")
        response = engine.generate(_req())
        assert response.finish_reason == "stop"

    def test_finish_reason_length(self, engine) -> None:
        engine._client.messages.create.return_value = _fake_response(stop_reason="max_tokens")
        response = engine.generate(_req())
        assert response.finish_reason == "length"

    def test_usage_populated(self, engine) -> None:
        engine._client.messages.create.return_value = _fake_response()
        response = engine.generate(_req())
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 20
        assert response.usage.total_tokens == 30

    def test_backend_field(self, engine) -> None:
        engine._client.messages.create.return_value = _fake_response()
        response = engine.generate(_req())
        assert response.backend == "anthropic"

    def test_system_message_passed_as_system_param(self, engine) -> None:
        engine._client.messages.create.return_value = _fake_response()
        request = GenerationRequest(messages=[
            ChatMessage(role="system", content="You are a tutor."),
            ChatMessage(role="user", content="Explain recursion."),
        ])
        engine.generate(request)
        call_kwargs = engine._client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a tutor."
        # system message should not be in messages list
        assert not any(m.get("role") == "system" for m in call_kwargs["messages"])

    def test_empty_messages_raises(self, engine) -> None:
        from llm_engines.contracts import GenerationError
        with pytest.raises(GenerationError):
            engine.generate(GenerationRequest(messages=[]))

    def test_capabilities_flags(self, engine) -> None:
        caps = engine.get_capabilities()
        assert caps.chat is True
        assert caps.async_streaming is True
        assert caps.tool_calling is True
        assert caps.embeddings is False
        assert caps.streaming is False  # sync streaming not supported

    def test_is_cloud_flag(self, engine) -> None:
        assert engine.is_cloud is True


# ---------------------------------------------------------------------------
# Tool calling
# ---------------------------------------------------------------------------

class TestAnthropicToolCalling:

    def test_tool_calls_extracted(self, engine) -> None:
        from llm_engines.contracts import ToolSpec, ToolParameterSchema
        engine._client.messages.create.return_value = _fake_response(
            content=[_fake_tool_block(id="call_1", name="get_weather", input={"city": "Paris"})],
            stop_reason="tool_use",
        )
        tool = ToolSpec(
            name="get_weather",
            description="Get weather for a city",
            parameters={"city": ToolParameterSchema(type="string", description="City name")},
            required_params=["city"],
        )
        response = engine.generate_with_tools(_req(), [tool])
        assert response.finish_reason == "tool_call"
        assert len(response.message.tool_calls) == 1
        assert response.message.tool_calls[0].name == "get_weather"
        assert response.message.tool_calls[0].arguments == {"city": "Paris"}
        assert response.message.tool_calls[0].call_id == "call_1"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

class TestAnthropicErrorMapping:

    def test_rate_limit_maps_to_rate_limit_error(self, engine) -> None:
        import anthropic
        from llm_engines.contracts import RateLimitError
        engine._client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limit", response=MagicMock(status_code=429), body={}
        )
        with pytest.raises(RateLimitError):
            engine.generate(_req())

    def test_connection_error_maps_to_backend_unavailable(self, engine) -> None:
        import anthropic
        from llm_engines.contracts import BackendUnavailableError
        engine._client.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock()
        )
        with pytest.raises(BackendUnavailableError):
            engine.generate(_req())
