"""
tests/contract_tests/test_mock_engine.py

Directly tests MockEngine to verify it passes conformance AND its own features.
These tests run with no external services and serve as a smoke test for the
contract test harness itself.
"""

from __future__ import annotations

import pytest

from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
)
from llm_engines.backends.mock import MockEngine


@pytest.fixture()
def engine() -> MockEngine:
    return MockEngine()


class TestMockEngineConformance:
    """MockEngine must satisfy all ChatModel contract requirements."""

    def test_returns_generation_response(self, engine: MockEngine) -> None:
        req = GenerationRequest(messages=[ChatMessage(role="user", content="Hi")])
        resp = engine.generate(req)
        assert isinstance(resp, GenerationResponse)

    def test_role_is_assistant(self, engine: MockEngine) -> None:
        req = GenerationRequest(messages=[ChatMessage(role="user", content="Hi")])
        resp = engine.generate(req)
        assert resp.message.role == "assistant"

    def test_backend_field(self, engine: MockEngine) -> None:
        req = GenerationRequest(messages=[ChatMessage(role="user", content="Hi")])
        resp = engine.generate(req)
        assert resp.backend == "mock"

    def test_usage_populated(self, engine: MockEngine) -> None:
        req = GenerationRequest(messages=[ChatMessage(role="user", content="Hello world")])
        resp = engine.generate(req)
        assert resp.usage.input_tokens is not None and resp.usage.input_tokens > 0
        assert resp.usage.output_tokens is not None and resp.usage.output_tokens > 0
        assert resp.usage.total_tokens == resp.usage.input_tokens + resp.usage.output_tokens


class TestMockEngineFeatures:
    """MockEngine-specific behaviour (not part of the Protocol contract)."""

    def test_call_count_increments(self, engine: MockEngine) -> None:
        req = GenerationRequest(messages=[ChatMessage(role="user", content="Hi")])
        engine.generate(req)
        engine.generate(req)
        assert engine.call_count == 2

    def test_reset_clears_call_count(self, engine: MockEngine) -> None:
        req = GenerationRequest(messages=[ChatMessage(role="user", content="Hi")])
        engine.generate(req)
        engine.reset()
        assert engine.call_count == 0

    def test_custom_response_fn(self) -> None:
        custom = MockEngine(response_fn=lambda req: "Custom!")
        req = GenerationRequest(messages=[ChatMessage(role="user", content="Hi")])
        resp = custom.generate(req)
        assert resp.message.content == "Custom!"

    def test_echoes_user_message(self, engine: MockEngine) -> None:
        req = GenerationRequest(messages=[ChatMessage(role="user", content="specific query")])
        resp = engine.generate(req)
        assert "specific query" in (resp.message.content or "")
