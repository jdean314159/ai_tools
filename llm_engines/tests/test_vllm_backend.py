"""
tests/test_vllm_backend.py

vLLMEngine offline unit tests. All HTTP is mocked.

Live tests: pytest -m vllm  (requires running vLLM server at localhost:8000)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai")

from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_model(id: str):
    return SimpleNamespace(id=id)


def _fake_models_list(*ids: str):
    return SimpleNamespace(data=[_fake_model(i) for i in ids])


def _fake_usage(prompt=8, completion=15):
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


def _fake_choice(content="vLLM response", finish_reason="stop"):
    return SimpleNamespace(
        message=SimpleNamespace(content=content, tool_calls=None),
        finish_reason=finish_reason,
    )


def _fake_completion(content="vLLM response", model="Qwen/Qwen2.5-32B-Instruct-AWQ"):
    return SimpleNamespace(
        id="cmpl_vllm_123",
        model=model,
        choices=[_fake_choice(content)],
        usage=_fake_usage(),
    )


def _make_engine(available_models=("Qwen/Qwen2.5-32B-Instruct-AWQ",)):
    with patch("openai.OpenAI") as MockSync, \
         patch("openai.AsyncOpenAI") as MockAsync:
        MockSync.return_value = MagicMock()
        MockSync.return_value.models.list.return_value = _fake_models_list(*available_models)
        MockAsync.return_value = MagicMock()

        from llm_engines.backends.vllm import vLLMEngine
        engine = vLLMEngine(
            model="Qwen/Qwen2.5-32B-Instruct-AWQ",
            base_url="http://localhost:8000/v1",
        )
        engine._client = MockSync.return_value
        engine._async_client = MockAsync.return_value
        return engine


@pytest.fixture()
def engine():
    return _make_engine()


def _req(content="Hello"):
    return GenerationRequest(messages=[ChatMessage(role="user", content=content)])


class TestVLLMGenerate:

    def test_returns_generation_response(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        resp = engine.generate(_req())
        assert isinstance(resp, GenerationResponse)
        assert resp.backend == "vllm"

    def test_uses_resolved_model(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        engine.generate(_req())
        kwargs = engine._client.chat.completions.create.call_args[1]
        assert kwargs["model"] == engine._resolved_model

    def test_usage_populated(self, engine) -> None:
        engine._client.chat.completions.create.return_value = _fake_completion()
        resp = engine.generate(_req())
        assert resp.usage.input_tokens == 8
        assert resp.usage.output_tokens == 15
        assert resp.usage.total_tokens == 23

    def test_empty_messages_raises(self, engine) -> None:
        from llm_engines.contracts import GenerationError
        with pytest.raises(GenerationError):
            engine.generate(GenerationRequest(messages=[]))

    def test_is_cloud_false(self, engine) -> None:
        assert engine.is_cloud is False


class TestVLLMModelResolution:

    def test_exact_match(self) -> None:
        engine = _make_engine(("Qwen/Qwen2.5-32B-Instruct-AWQ",))
        assert engine._resolved_model == "Qwen/Qwen2.5-32B-Instruct-AWQ"

    def test_suffix_match(self) -> None:
        """Short alias 'qwen-32b-awq' should resolve against full HF ID."""
        with patch("openai.OpenAI") as MockSync, patch("openai.AsyncOpenAI"):
            MockSync.return_value = MagicMock()
            MockSync.return_value.models.list.return_value = _fake_models_list(
                "Qwen/Qwen2.5-32B-Instruct-AWQ"
            )
            from llm_engines.backends.vllm import vLLMEngine
            engine = vLLMEngine(model="Qwen2.5-32B-Instruct-AWQ")
        assert "Qwen2.5-32B-Instruct-AWQ" in engine._resolved_model

    def test_fallback_when_server_unreachable(self) -> None:
        """Model resolution failure should not raise — use configured name."""
        import openai
        with patch("openai.OpenAI") as MockSync, patch("openai.AsyncOpenAI"):
            MockSync.return_value = MagicMock()
            MockSync.return_value.models.list.side_effect = (
                openai.APIConnectionError(request=MagicMock())
            )
            from llm_engines.backends.vllm import vLLMEngine
            engine = vLLMEngine(model="my-model")
        # Should not raise — falls back to configured name
        assert engine._resolved_model == "my-model"

    def test_fallback_to_first_available_when_no_match(self) -> None:
        """When configured model not found, use first available."""
        engine = _make_engine(("SomeOtherModel/v1",))
        assert engine._resolved_model == "SomeOtherModel/v1"


class TestVLLMLogprobs:

    def test_logprob_result_structure(self, engine) -> None:
        from llm_engines.contracts import LogprobResult

        fake_tlp = SimpleNamespace(token="hello", logprob=-0.5, bytes=None)
        fake_logprob_content = SimpleNamespace(content=[fake_tlp])
        fake_choice = SimpleNamespace(
            message=SimpleNamespace(content="hello"),
            finish_reason="stop",
            logprobs=fake_logprob_content,
        )
        engine._client.chat.completions.create.return_value = SimpleNamespace(
            id="lp_1",
            model="test",
            choices=[fake_choice],
            usage=_fake_usage(),
        )

        result = engine.generate_with_logprobs(_req())
        assert isinstance(result, LogprobResult)
        assert result.text == "hello"
        assert len(result.token_logprobs) == 1
        assert result.token_logprobs[0].logprob == -0.5

    def test_perplexity_computed(self, engine) -> None:
        import math
        fake_tlps = [
            SimpleNamespace(token="A", logprob=-1.0, bytes=None),
            SimpleNamespace(token="B", logprob=-1.0, bytes=None),
        ]
        fake_choice = SimpleNamespace(
            message=SimpleNamespace(content="AB"),
            finish_reason="stop",
            logprobs=SimpleNamespace(content=fake_tlps),
        )
        engine._client.chat.completions.create.return_value = SimpleNamespace(
            id="lp_2", model="test",
            choices=[fake_choice], usage=_fake_usage(),
        )
        result = engine.generate_with_logprobs(_req())
        expected_perplexity = math.exp(1.0)
        assert abs(result.perplexity - expected_perplexity) < 0.001


class TestVLLMCapabilities:

    def test_capabilities(self, engine) -> None:
        caps = engine.get_capabilities()
        assert caps.chat is True
        assert caps.async_streaming is True
        assert caps.batch_generation is True
        assert caps.logprobs is True
        assert caps.tool_calling is False  # not wired yet
        assert caps.embeddings is False


class TestVLLMErrors:

    def test_connection_error_maps_to_backend_unavailable(self, engine) -> None:
        import openai
        from llm_engines.contracts import BackendUnavailableError
        engine._client.chat.completions.create.side_effect = (
            openai.APIConnectionError(request=MagicMock())
        )
        with pytest.raises(BackendUnavailableError):
            engine.generate(_req())

    def test_context_length_error(self, engine) -> None:
        import openai
        from llm_engines.contracts import ContextLengthExceededError
        engine._client.chat.completions.create.side_effect = openai.BadRequestError(
            message="max_model_len exceeded",
            response=MagicMock(status_code=400, headers={}),
            body={"error": {"message": "max_model_len"}},
        )
        with pytest.raises(ContextLengthExceededError):
            engine.generate(_req())


@pytest.mark.vllm
class TestVLLMLive:
    """Live tests — require vLLM server at localhost:8000."""

    def test_generate_live(self) -> None:
        from llm_engines.backends.vllm import vLLMEngine
        engine = vLLMEngine(model="auto")  # will resolve from /v1/models
        resp = engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content="Say: OK")],
            max_tokens=10,
            temperature=0.0,
        ))
        assert resp.message.content is not None
        assert resp.backend == "vllm"

    def test_logprobs_live(self) -> None:
        from llm_engines.backends.vllm import vLLMEngine
        engine = vLLMEngine(model="auto")
        result = engine.generate_with_logprobs(GenerationRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            max_tokens=5,
        ))
        assert len(result.token_logprobs) > 0
        assert result.perplexity > 0
