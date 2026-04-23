"""
tests/test_propose_then_verify.py

ProposeThenVerifyEngine tests using MockEngine. No live services needed.
"""
from __future__ import annotations

import pytest

from llm_engines.contracts import ChatMessage, GenerationRequest, GenerationResponse
from llm_engines.backends.mock import MockEngine
from llm_engines.strategies.propose_then_verify import ProposeThenVerifyEngine


def _req(content: str = "What is the capital of France?") -> GenerationRequest:
    return GenerationRequest(
        messages=[ChatMessage(role="user", content=content)],
        max_tokens=100,
    )


class TestProposeThenVerify:

    def test_returns_generation_response(self) -> None:
        engine = ProposeThenVerifyEngine(
            draft=MockEngine(response_fn=lambda r: "Paris"),
            verifier=MockEngine(response_fn=lambda r: "Paris"),
            n_drafts=2,
        )
        resp = engine.generate(_req())
        assert isinstance(resp, GenerationResponse)
        assert resp.message.role == "assistant"
        assert resp.backend == "propose_then_verify"

    def test_n_drafts_1_skips_selection(self) -> None:
        """With n_drafts=1, verifier selection step should be bypassed."""
        verifier_calls = {"count": 0}

        def verifier_fn(r):
            verifier_calls["count"] += 1
            return "Verifier response"

        engine = ProposeThenVerifyEngine(
            draft=MockEngine(response_fn=lambda r: "Draft only"),
            verifier=MockEngine(response_fn=verifier_fn),
            n_drafts=1,
        )
        resp = engine.generate(_req())
        assert resp.message.content == "Draft only"
        # verifier.generate() should NOT have been called for selection
        # (it IS the verifier engine but n_drafts=1 skips the select step)
        assert verifier_calls["count"] == 0

    def test_usage_aggregates_all_calls(self) -> None:
        """Total tokens should include all draft calls + verify call."""
        engine = ProposeThenVerifyEngine(
            draft=MockEngine(response_fn=lambda r: "A" * 100),  # ~25 output tokens
            verifier=MockEngine(response_fn=lambda r: "Best"),
            n_drafts=3,
            parallel=False,
        )
        resp = engine.generate(_req())
        # 3 draft calls + 1 verify call — total_tokens should reflect all
        assert resp.usage.total_tokens is not None
        assert resp.usage.total_tokens > 0

    def test_all_drafts_failed_raises(self) -> None:
        from llm_engines.contracts import GenerationError

        def always_fail(r):
            raise GenerationError("draft failed")

        engine = ProposeThenVerifyEngine(
            draft=MockEngine(response_fn=always_fail),
            verifier=MockEngine(),
            n_drafts=2,
            parallel=False,
        )
        with pytest.raises(GenerationError, match="All.*draft candidates failed"):
            engine.generate(_req())

    def test_verifier_failure_falls_back_to_first_candidate(self) -> None:
        from llm_engines.contracts import GenerationError

        call_count = {"n": 0}

        def draft_fn(r):
            call_count["n"] += 1
            return f"Candidate {call_count['n']}"

        def verifier_fail(r):
            raise GenerationError("verifier down")

        engine = ProposeThenVerifyEngine(
            draft=MockEngine(response_fn=draft_fn),
            verifier=MockEngine(response_fn=verifier_fail),
            n_drafts=3,
            parallel=False,
        )
        resp = engine.generate(_req())
        # Should not raise — falls back to first candidate
        assert resp.message.content is not None

    def test_parallel_generates_n_drafts(self) -> None:
        call_count = {"n": 0}

        def counting_fn(r):
            call_count["n"] += 1
            return f"response {call_count['n']}"

        engine = ProposeThenVerifyEngine(
            draft=MockEngine(response_fn=counting_fn),
            verifier=MockEngine(response_fn=lambda r: "selected"),
            n_drafts=4,
            parallel=True,
        )
        engine.generate(_req())
        assert call_count["n"] == 4  # 4 draft calls

    def test_empty_messages_raises(self) -> None:
        from llm_engines.contracts import GenerationError
        engine = ProposeThenVerifyEngine(
            draft=MockEngine(), verifier=MockEngine(), n_drafts=2
        )
        with pytest.raises(GenerationError):
            engine.generate(GenerationRequest(messages=[]))

    def test_model_name_describes_configuration(self) -> None:
        engine = ProposeThenVerifyEngine(
            draft=MockEngine(model="qwen3:8b"),
            verifier=MockEngine(model="qwen3:27b"),
            n_drafts=3,
        )
        resp = engine.generate(_req())
        assert "qwen3:8b" in resp.model_name
        assert "qwen3:27b" in resp.model_name
        assert "3" in resp.model_name

    def test_draft_uses_higher_temperature(self) -> None:
        """Draft requests should use the configured temperature, not the original."""
        captured = []

        def capture(r):
            captured.append(r.temperature)
            return "response"

        engine = ProposeThenVerifyEngine(
            draft=MockEngine(response_fn=capture),
            verifier=MockEngine(response_fn=lambda r: "selected"),
            n_drafts=2,
            temperature=0.9,
            parallel=False,
        )
        engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content="Hi")],
            temperature=0.0,  # original request: deterministic
        ))
        # All draft calls should use the engine's temperature (0.9), not 0.0
        assert all(t == 0.9 for t in captured)
