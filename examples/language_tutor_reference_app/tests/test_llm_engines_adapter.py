"""
test_llm_engines_adapter.py

Contract tests for LLMEnginesAdapter against MockEngine.

These verify that the adapter correctly bridges the tutor's string-based engine
interface to the llm_engines GenerationRequest/GenerationResponse protocol,
without requiring any external services.
"""

from __future__ import annotations

import json
from pydantic import BaseModel

from llm_engines.backends.mock import MockEngine
from language_tutor.llm_engines_adapter import LLMEnginesAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _adapter(response_fn=None, model: str = "mock-1b") -> LLMEnginesAdapter:
    engine = MockEngine(model=model, response_fn=response_fn)
    return LLMEnginesAdapter(engine, model_name=model)


class _Plan(BaseModel):
    topic: str = "daily life"
    difficulty: str = "beginner"


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


def test_generate_returns_nonempty_string():
    adapter = _adapter()
    result = adapter.generate("Hola, ¿cómo estás?")
    assert isinstance(result, str)
    assert result.strip()


def test_generate_passes_system_prompt_as_system_message():
    captured = {}

    def _record(req):
        captured["messages"] = req.messages
        return "ok"

    adapter = _adapter(response_fn=_record)
    adapter.generate("Hello", system_prompt="You are a Spanish tutor.")

    roles = [m.role for m in captured["messages"]]
    assert roles[0] == "system"
    assert roles[-1] == "user"
    assert "Spanish tutor" in captured["messages"][0].content


def test_generate_without_system_prompt_sends_only_user_message():
    captured = {}

    def _record(req):
        captured["messages"] = req.messages
        return "ok"

    adapter = _adapter(response_fn=_record)
    adapter.generate("Hello")
    assert all(m.role == "user" for m in captured["messages"])


def test_generate_passes_max_tokens():
    captured = {}

    def _record(req):
        captured["max_tokens"] = req.max_tokens
        return "ok"

    adapter = _adapter(response_fn=_record)
    adapter.generate("test", max_tokens=999)
    assert captured["max_tokens"] == 999


def test_generate_returns_empty_string_when_content_is_none(monkeypatch):
    from llm_engines.contracts import ChatMessage, GenerationResponse, UsageStats

    engine = MockEngine()

    def _null_generate(request):
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=None),
            finish_reason="stop",
            usage=UsageStats(input_tokens=1, output_tokens=0, total_tokens=1, latency_ms=0.0),
            model_name="mock",
            backend="mock",
        )

    monkeypatch.setattr(engine, "generate", _null_generate)
    adapter = LLMEnginesAdapter(engine)
    assert adapter.generate("test") == ""


# ---------------------------------------------------------------------------
# count_tokens()
# ---------------------------------------------------------------------------


def test_count_tokens_returns_positive_int():
    adapter = _adapter()
    count = adapter.count_tokens("El niño bebe agua.")
    assert isinstance(count, int)
    assert count > 0


def test_count_tokens_empty_string():
    adapter = _adapter()
    count = adapter.count_tokens("")
    assert isinstance(count, int)


def test_count_tokens_longer_text_is_more_than_shorter():
    adapter = _adapter()
    short = adapter.count_tokens("Hola")
    long = adapter.count_tokens("El niño bebe agua en el parque con sus amigos.")
    assert long > short


# ---------------------------------------------------------------------------
# generate_structured()
# ---------------------------------------------------------------------------


def test_generate_structured_returns_pydantic_model():
    def _json_response(req):
        return json.dumps({"topic": "food", "difficulty": "intermediate"})

    adapter = _adapter(response_fn=_json_response)
    result = adapter.generate_structured("Generate a plan.", response_model=_Plan)
    assert isinstance(result, _Plan)
    assert result.topic == "food"
    assert result.difficulty == "intermediate"


def test_generate_structured_handles_markdown_fenced_json():
    def _fenced(req):
        return '```json\n{"topic": "travel", "difficulty": "advanced"}\n```'

    adapter = _adapter(response_fn=_fenced)
    result = adapter.generate_structured("Generate a plan.", response_model=_Plan)
    assert isinstance(result, _Plan)
    assert result.topic == "travel"


def test_generate_structured_injects_schema_into_prompt():
    captured = {}

    def _record(req):
        captured["prompt"] = req.messages[-1].content
        return json.dumps({"topic": "verbs", "difficulty": "beginner"})

    adapter = _adapter(response_fn=_record)
    adapter.generate_structured("Generate a plan.", response_model=_Plan)
    # Schema instructions should be in the prompt
    assert "topic" in captured["prompt"] or "Plan" in captured["prompt"]


# ---------------------------------------------------------------------------
# generate_with_logprobs()
# ---------------------------------------------------------------------------


def test_generate_with_logprobs_returns_none_for_non_logprob_engine():
    # MockEngine does not implement LogprobModel
    adapter = _adapter()
    result = adapter.generate_with_logprobs("test")
    assert result is None


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


def test_stream_yields_string_chunks_when_streaming_not_supported():
    # MockEngine does not implement StreamingModel — falls back to generate
    adapter = _adapter()
    chunks = list(adapter.stream("Hola"))
    assert chunks
    assert all(isinstance(c, str) for c in chunks)
    full_text = "".join(chunks)
    assert full_text.strip()


# ---------------------------------------------------------------------------
# model_name
# ---------------------------------------------------------------------------


def test_model_name_taken_from_engine_when_not_passed():
    engine = MockEngine(model="test-model-xyz")
    adapter = LLMEnginesAdapter(engine)
    assert adapter.model_name == "test-model-xyz"


def test_model_name_explicit_overrides_engine():
    engine = MockEngine(model="engine-model")
    adapter = LLMEnginesAdapter(engine, model_name="explicit-model")
    assert adapter.model_name == "explicit-model"


# ---------------------------------------------------------------------------
# call counting via MockEngine.call_count
# ---------------------------------------------------------------------------


def test_call_count_increments_on_each_generate():
    engine = MockEngine()
    adapter = LLMEnginesAdapter(engine)
    assert engine.call_count == 0
    adapter.generate("one")
    assert engine.call_count == 1
    adapter.generate("two")
    assert engine.call_count == 2
