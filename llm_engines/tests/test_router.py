"""
tests/test_router.py

FailoverEngine unit tests. All tests use MockEngine — no external services.
"""

from __future__ import annotations

import pytest

from llm_engines.contracts import (
    ChatMessage,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
)
from llm_engines.backends.mock import MockEngine
from llm_engines.router import FailoverEngine, FailoverPolicy


def _req(content: str = "Hello") -> GenerationRequest:
    return GenerationRequest(messages=[ChatMessage(role="user", content=content)])


def _always_fail(request: GenerationRequest) -> str:
    raise GenerationError("Deliberate test failure")


def _fail_then_succeed(n_failures: int):
    """Returns a response_fn that fails n times then succeeds."""
    calls = {"count": 0}

    def fn(request: GenerationRequest) -> str:
        calls["count"] += 1
        if calls["count"] <= n_failures:
            raise GenerationError(f"Deliberate failure #{calls['count']}")
        return "Success after failures"

    return fn


class TestFailoverEngineBasic:
    def test_single_engine_success(self) -> None:
        engine = FailoverEngine([MockEngine()])
        response = engine.generate(_req())
        assert isinstance(response, GenerationResponse)
        assert response.message.role == "assistant"

    def test_failover_to_second_engine(self) -> None:
        primary = MockEngine(response_fn=_always_fail)
        fallback = MockEngine(response_fn=lambda r: "Fallback response")
        engine = FailoverEngine(
            [primary, fallback],
            policy=FailoverPolicy(max_attempts=4, transient_retry=False),
        )
        response = engine.generate(_req())
        assert response.message.content == "Fallback response"

    def test_all_engines_fail_raises(self) -> None:
        engines = [
            MockEngine(response_fn=_always_fail),
            MockEngine(response_fn=_always_fail),
        ]
        engine = FailoverEngine(
            engines,
            policy=FailoverPolicy(max_attempts=4, transient_retry=False),
        )
        with pytest.raises(GenerationError, match="All engines failed"):
            engine.generate(_req())

    def test_empty_engines_raises_at_construction(self) -> None:
        with pytest.raises(ValueError, match="at least one engine"):
            FailoverEngine([])


class TestCircuitBreaker:
    def test_circuit_trips_after_n_failures(self) -> None:
        failing = MockEngine(response_fn=_always_fail)
        healthy = MockEngine(response_fn=lambda r: "Healthy")
        policy = FailoverPolicy(
            circuit_breaker_failures=2,
            circuit_breaker_cooldown_s=60.0,
            transient_retry=False,
            max_attempts=10,
        )
        engine = FailoverEngine([failing, healthy], policy=policy)
        # Drive enough failures to trip the circuit breaker
        for _ in range(3):
            try:
                engine.generate(_req())
            except Exception:
                pass

        # After tripping, should route directly to healthy engine
        response = engine.generate(_req())
        assert response.message.content == "Healthy"

    def test_reset_health_clears_circuit(self) -> None:
        always_failing = MockEngine(response_fn=_always_fail)
        policy = FailoverPolicy(
            circuit_breaker_failures=1,
            circuit_breaker_cooldown_s=9999.0,
            transient_retry=False,
            max_attempts=4,
        )
        engine = FailoverEngine([always_failing], policy=policy)
        # Trip the circuit
        try:
            engine.generate(_req())
        except Exception:
            pass
        # Reset
        engine.reset_health()
        # Health report shows engine is healthy again
        report = engine.health_report()
        assert all(v["healthy"] for v in report.values())


class TestCapabilities:
    def test_capabilities_are_union(self) -> None:
        # One engine reports embeddings=True
        class EmbedMock(MockEngine):
            def get_capabilities(self):
                caps = super().get_capabilities()
                return caps.model_copy(update={"embeddings": True})

        engine = FailoverEngine([MockEngine(), EmbedMock()])
        assert engine.get_capabilities().embeddings is True

    def test_chat_always_true_with_any_engine(self) -> None:
        engine = FailoverEngine([MockEngine()])
        assert engine.get_capabilities().chat is True


class TestStreaming:
    def test_stream_falls_back_to_generate(self) -> None:
        """MockEngine doesn't implement StreamingModel; fallback to generate()."""
        engine = FailoverEngine([MockEngine()])
        req = _req("Stream test")
        tokens = list(engine.stream(req))
        assert len(tokens) > 0
        assert isinstance(tokens[0], str)


class TestOOMReduction:
    def test_oom_reduces_max_tokens(self) -> None:
        """OOM on first engine should reduce max_tokens, not trip circuit breaker."""
        call_log: list[int] = []

        def oom_on_large(request: GenerationRequest) -> str:
            call_log.append(request.max_tokens)
            if request.max_tokens > 256:
                raise GenerationError("cuda out of memory")
            return "OK after reduction"

        engine = FailoverEngine(
            [MockEngine(response_fn=oom_on_large)],
            policy=FailoverPolicy(
                reduce_output_on_oom=True,
                min_max_tokens=128,
                transient_retry=False,
                max_attempts=6,
            ),
        )
        response = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content="Hi")],
                max_tokens=1024,
            )
        )
        assert response.message.content == "OK after reduction"
        # max_tokens should have been reduced at least once
        assert any(t <= 512 for t in call_log)


class TestCloudPolicy:
    def test_cloud_sanitise_strips_memory_block(self) -> None:
        """Requests to cloud engines should have memory blocks stripped."""
        from llm_engines.router import _sanitise_for_cloud

        request = GenerationRequest(
            messages=[
                ChatMessage(role="system", content="You are a helpful assistant."),
                ChatMessage(role="user", content="--- retrieved context ---\nsome memory\n---"),
                ChatMessage(role="user", content="What should I do?"),
            ]
        )
        sanitised = _sanitise_for_cloud(request, "query_only")
        # Memory block message should be gone
        contents = [m.content for m in sanitised.messages]
        assert not any("retrieved context" in (c or "") for c in contents)

    def test_full_context_passes_through(self) -> None:
        from llm_engines.router import _sanitise_for_cloud

        request = GenerationRequest(
            messages=[
                ChatMessage(role="user", content="--- retrieved context ---\nmemory\n---"),
            ]
        )
        sanitised = _sanitise_for_cloud(request, "full_context")
        assert sanitised.messages == request.messages


class TestHealthReport:
    def test_health_report_keys_match_engines(self) -> None:
        engines = [MockEngine(model="a"), MockEngine(model="b")]
        failover = FailoverEngine(engines)
        report = failover.health_report()
        assert len(report) == len(engines)
        assert all(v["healthy"] for v in report.values())
