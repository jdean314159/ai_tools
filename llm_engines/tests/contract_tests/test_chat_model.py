"""
tests/contract_tests/test_chat_model.py

Conformance tests for the ChatModel Protocol (ADR-001, ADR-002).
Every backend that declares ChatModel must pass all tests here.

Run against a specific backend:
    pytest tests/contract_tests/test_chat_model.py --backend mock
    pytest tests/contract_tests/test_chat_model.py --backend ollama --model qwen2.5:8b

Backends under test are parameterized via conftest.py fixtures.
"""
from __future__ import annotations

import pytest
from typing import get_args

from llm_engines.contracts import (
    ChatMessage,
    ChatModel,
    EngineCapabilities,
    FinishReason,
    GenerationRequest,
    GenerationResponse,
    UsageStats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_request(content: str = "Hello") -> GenerationRequest:
    return GenerationRequest(
        messages=[ChatMessage(role="user", content=content)]
    )


# ---------------------------------------------------------------------------
# Conformance: get_capabilities()
# ---------------------------------------------------------------------------

class TestGetCapabilities:

    def test_returns_engine_capabilities(self, chat_engine: ChatModel) -> None:
        caps = chat_engine.get_capabilities()
        assert isinstance(caps, EngineCapabilities)

    def test_chat_is_always_true(self, chat_engine: ChatModel) -> None:
        caps = chat_engine.get_capabilities()
        assert caps.chat is True, "chat capability must be True for all ChatModel engines"

    def test_capabilities_are_bool(self, chat_engine: ChatModel) -> None:
        caps = chat_engine.get_capabilities()
        bool_fields = [
            caps.chat, caps.streaming, caps.async_streaming, caps.tool_calling,
            caps.embeddings, caps.structured_output, caps.batch_generation,
            caps.vision, caps.usage_reporting, caps.logprobs,
        ]
        assert all(isinstance(v, bool) for v in bool_fields)


# ---------------------------------------------------------------------------
# Conformance: generate()
# ---------------------------------------------------------------------------

class TestGenerate:

    def test_returns_generation_response(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        assert isinstance(response, GenerationResponse), (
            "generate() must return GenerationResponse, not str or dict"
        )

    def test_message_is_chat_message(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        assert isinstance(response.message, ChatMessage)

    def test_message_role_is_assistant(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        assert response.message.role == "assistant"

    def test_message_has_content(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        assert response.message.content is not None
        assert len(response.message.content) > 0

    def test_finish_reason_is_valid(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        valid = get_args(FinishReason)
        assert response.finish_reason in valid, (
            f"finish_reason '{response.finish_reason}' not in {valid}"
        )

    def test_model_name_is_non_empty(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        assert isinstance(response.model_name, str)
        assert len(response.model_name) > 0

    def test_backend_is_non_empty(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        assert isinstance(response.backend, str)
        assert len(response.backend) > 0

    def test_usage_is_usage_stats(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        assert isinstance(response.usage, UsageStats)

    def test_usage_tokens_non_negative_when_reported(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        u = response.usage
        if u.input_tokens is not None:
            assert u.input_tokens >= 0
        if u.output_tokens is not None:
            assert u.output_tokens >= 0
        if u.total_tokens is not None:
            assert u.total_tokens >= 0

    def test_usage_latency_non_negative_when_reported(self, chat_engine: ChatModel) -> None:
        response = chat_engine.generate(_minimal_request())
        if response.usage.latency_ms is not None:
            assert response.usage.latency_ms >= 0.0

    def test_system_message_accepted(self, chat_engine: ChatModel) -> None:
        request = GenerationRequest(messages=[
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="What is 2+2?"),
        ])
        response = chat_engine.generate(request)
        assert isinstance(response, GenerationResponse)

    def test_max_tokens_respected(self, chat_engine: ChatModel) -> None:
        """Output should not be dramatically longer than max_tokens allows."""
        request = GenerationRequest(
            messages=[ChatMessage(role="user", content="Count from 1 to 1000.")],
            max_tokens=20,
        )
        response = chat_engine.generate(request)
        # finish_reason "length" or "stop"; content should be short
        content = response.message.content or ""
        # 20 tokens ≈ 80 chars; allow 2x headroom for tokenizer variation
        assert len(content) < 300, (
            f"Response too long for max_tokens=20: {len(content)} chars"
        )

    def test_generate_is_deterministic_at_zero_temperature(
        self, chat_engine: ChatModel
    ) -> None:
        """Two calls at temperature=0 should return identical content."""
        request = GenerationRequest(
            messages=[ChatMessage(role="user", content="What is the capital of France?")],
            temperature=0.0,
            max_tokens=50,
        )
        r1 = chat_engine.generate(request)
        r2 = chat_engine.generate(request)
        assert r1.message.content == r2.message.content, (
            "At temperature=0, generate() must be deterministic"
        )


# ---------------------------------------------------------------------------
# Conformance: error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_empty_messages_raises(self, chat_engine: ChatModel) -> None:
        """An empty messages list is invalid and must raise."""
        with pytest.raises(Exception):  # pydantic ValidationError or LLMEngineError
            chat_engine.generate(GenerationRequest(messages=[]))

    def test_does_not_raise_raw_http_errors(self, chat_engine: ChatModel) -> None:
        """
        Backend must wrap transport errors in LLMEngineError subclasses.
        This test only applies to live backends; mock passes trivially.
        """
        # For the mock engine this always passes.
        # Live backend tests should override or mark this for skip when offline.
        try:
            chat_engine.generate(_minimal_request())
        except Exception as e:
            from llm_engines.contracts import LLMEngineError
            assert isinstance(e, LLMEngineError), (
                f"Expected LLMEngineError subclass, got {type(e).__name__}: {e}"
            )
