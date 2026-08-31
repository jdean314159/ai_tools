"""
llm_engines/backends/mock.py

MockEngine: deterministic in-process engine for unit testing.

Supports: ChatModel only.
Does not require any external services or GPU.
"""

from __future__ import annotations

from typing import Callable

from llm_engines.contracts import (
    ChatMessage,
    EngineCapabilities,
    GenerationRequest,
    GenerationResponse,
    UsageStats,
)


class MockEngine:
    """
    Deterministic engine for unit and conformance tests.

    By default returns a fixed canned response. Optionally accepts a
    callable that receives the request and returns a string, allowing
    per-test control over output.

    Usage:
        engine = MockEngine()
        response = engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content="Hello")]
        ))
        assert response.message.content == "Mock response."

        # Custom response
        engine = MockEngine(response_fn=lambda req: "Custom output")
    """

    BACKEND = "mock"

    def __init__(
        self,
        model: str = "mock-1b",
        response_fn: Callable[[GenerationRequest], str] | None = None,
        latency_ms: float = 0.1,
    ) -> None:
        self.model = model
        self._response_fn = response_fn
        self._latency_ms = latency_ms
        self._call_count = 0

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            chat=True,
            streaming=False,
            async_streaming=False,
            tool_calling=False,
            embeddings=False,
            structured_output=False,
            batch_generation=False,
            vision=False,
            usage_reporting=True,
            logprobs=False,
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not request.messages:
            from llm_engines.contracts import GenerationError

            raise GenerationError("MockEngine: messages list cannot be empty")

        self._call_count += 1

        if self._response_fn is not None:
            content = self._response_fn(request)
        else:
            last_user = next(
                (m.content for m in reversed(request.messages) if m.role == "user"),
                None,
            )
            content = f"Mock response to: {last_user}" if last_user else "Mock response."

        # Rough token estimate: 1 token ≈ 4 chars
        input_text = " ".join(m.content or "" for m in request.messages)
        input_tokens = max(1, len(input_text) // 4)
        output_tokens = max(1, len(content) // 4)

        return GenerationResponse(
            message=ChatMessage(role="assistant", content=content),
            finish_reason="stop",
            usage=UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                latency_ms=self._latency_ms,
            ),
            model_name=self.model,
            backend=self.BACKEND,
            seed_status="accepted" if request.seed is not None else "not_requested",
        )

    # ------------------------------------------------------------------
    # Test helpers (not part of any Protocol)
    # ------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        """Number of generate() calls made against this instance."""
        return self._call_count

    def reset(self) -> None:
        """Reset call counter. Useful between test cases."""
        self._call_count = 0
