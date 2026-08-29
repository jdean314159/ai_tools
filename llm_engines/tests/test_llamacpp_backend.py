from __future__ import annotations

import importlib
import sys
import types

import pytest

from llm_engines.contracts import ChatMessage, EngineConfigError, GenerationRequest


def test_llamacpp_forwards_json_schema_to_response_format(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }

    engine.generate(
        GenerationRequest(
            messages=[ChatMessage(role="user", content="Summarize")],
            json_schema=schema,
        )
    )

    assert engine._llm.calls[0]["response_format"] == {  # noqa: SLF001
        "type": "json_object",
        "schema": schema,
    }


def test_llamacpp_inlines_nested_json_schema_refs(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")
    schema = _nested_schema()

    engine.generate(
        GenerationRequest(
            messages=[ChatMessage(role="user", content="Summarize")],
            json_schema=schema,
        )
    )

    payload_schema = engine._llm.calls[0]["response_format"]["schema"]  # noqa: SLF001
    assert "$defs" not in payload_schema
    assert "$ref" not in str(payload_schema)
    assert payload_schema["properties"]["concern"]["type"] == "object"
    assert payload_schema["properties"]["concern"]["properties"]["finding_ref"]["type"] == "string"
    assert schema["properties"]["concern"]["$ref"] == "#/$defs/Concern"


def test_llamacpp_omits_response_format_without_json_schema(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")

    engine.generate(GenerationRequest(messages=[ChatMessage(role="user", content="Hi")]))

    assert "response_format" not in engine._llm.calls[0]  # noqa: SLF001


def test_llamacpp_forwards_seed_zero_and_reports_acceptance(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")

    response = engine.generate(
        GenerationRequest(messages=[ChatMessage(role="user", content="Hi")], seed=0)
    )

    assert engine._llm.calls[0]["seed"] == 0  # noqa: SLF001
    assert response.seed_status == "accepted"


def test_llamacpp_think_false_appends_no_think_to_last_user_message(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf", think=False)

    engine.generate(
        GenerationRequest(
            messages=[
                ChatMessage(role="system", content="Be concise"),
                ChatMessage(role="user", content="First"),
                ChatMessage(role="assistant", content="OK"),
                ChatMessage(role="user", content="Summarize"),
            ]
        )
    )

    messages = engine._llm.calls[0]["messages"]  # noqa: SLF001
    assert messages[0]["content"] == "Be concise"
    assert messages[1]["content"] == "First"
    assert messages[3]["content"] == "Summarize /no_think"


def test_llamacpp_think_false_appends_no_think_for_logprobs(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf", think=False)

    engine.generate_with_logprobs(
        GenerationRequest(messages=[ChatMessage(role="user", content="Score this")])
    )

    messages = engine._llm.calls[0]["messages"]  # noqa: SLF001
    assert messages[0]["content"] == "Score this /no_think"


def test_llamacpp_think_true_does_not_append_no_think(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf", think=True)

    engine.generate(GenerationRequest(messages=[ChatMessage(role="user", content="Hi")]))

    messages = engine._llm.calls[0]["messages"]  # noqa: SLF001
    assert messages[0]["content"] == "Hi"


def test_llamacpp_reports_structured_output_capability(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")

    assert engine.get_capabilities().structured_output is True


def test_llamacpp_count_tokens_uses_backend_tokenizer(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")

    assert engine.count_tokens("tokenize me") == 3
    assert engine._llm.tokenized == [b"tokenize me"]  # noqa: SLF001


def test_llamacpp_defaults_kv_cache_to_f16(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")

    assert engine._llm.kwargs["type_k"] == 101  # noqa: SLF001
    assert engine._llm.kwargs["type_v"] == 101  # noqa: SLF001


def test_llamacpp_omits_batch_kwargs_by_default(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")

    assert "n_batch" not in engine._llm.kwargs  # noqa: SLF001
    assert "n_ubatch" not in engine._llm.kwargs  # noqa: SLF001


def test_llamacpp_omits_flash_attn_by_default(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")

    assert "flash_attn" not in engine._llm.kwargs  # noqa: SLF001


def test_llamacpp_forwards_flash_attn_when_true(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(
        model_path="/models/test.gguf",
        flash_attn=True,
    )

    assert engine._llm.kwargs["flash_attn"] is True  # noqa: SLF001


def test_llamacpp_forwards_batch_kwargs_when_set(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(
        model_path="/models/test.gguf",
        n_batch=128,
        n_ubatch=64,
    )

    assert engine._llm.kwargs["n_batch"] == 128  # noqa: SLF001
    assert engine._llm.kwargs["n_ubatch"] == 64  # noqa: SLF001


def test_llamacpp_rejects_invalid_n_batch(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)

    with pytest.raises(EngineConfigError, match="n_batch must be >= 1"):
        module.LlamaCppEngine(model_path="/models/test.gguf", n_batch=0)


def test_llamacpp_rejects_invalid_n_ubatch(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)

    with pytest.raises(EngineConfigError, match="n_ubatch must be >= 1"):
        module.LlamaCppEngine(model_path="/models/test.gguf", n_ubatch=0)


def test_llamacpp_rejects_n_ubatch_larger_than_n_batch(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)

    with pytest.raises(EngineConfigError, match="n_ubatch must be <= n_batch"):
        module.LlamaCppEngine(
            model_path="/models/test.gguf",
            n_batch=128,
            n_ubatch=256,
        )


def test_llamacpp_forwards_quantized_kv_cache_types(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(
        model_path="/models/test.gguf",
        cache_type_k="q8_0",
        cache_type_v="q4_0",
    )

    assert engine._llm.kwargs["type_k"] == 108  # noqa: SLF001
    assert engine._llm.kwargs["type_v"] == 102  # noqa: SLF001


def test_llamacpp_rejects_unknown_kv_cache_type(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)

    with pytest.raises(EngineConfigError, match="Unsupported cache_type_k"):
        module.LlamaCppEngine(model_path="/models/test.gguf", cache_type_k="q5_0")


def _load_llamacpp_with_fake_dependency(monkeypatch):
    fake_module = types.ModuleType("llama_cpp")
    fake_module.GGML_TYPE_F16 = 101
    fake_module.GGML_TYPE_Q8_0 = 108
    fake_module.GGML_TYPE_Q4_0 = 102
    fake_module.Llama = _FakeLlama
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_module)
    sys.modules.pop("llm_engines.backends.llamacpp", None)
    return importlib.import_module("llm_engines.backends.llamacpp")


class _FakeLlama:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.calls: list[dict] = []
        self.tokenized: list[bytes] = []

    def tokenize(self, text: bytes) -> list[int]:
        self.tokenized.append(text)
        return [1, 2, 3]

    def create_chat_completion(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {
            "choices": [
                {
                    "message": {"content": '{"summary":"ok"}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 4,
            },
        }


def _nested_schema() -> dict:
    return {
        "$defs": {
            "Concern": {
                "type": "object",
                "properties": {"finding_ref": {"type": "string"}},
                "required": ["finding_ref"],
            }
        },
        "type": "object",
        "properties": {"concern": {"$ref": "#/$defs/Concern"}},
        "required": ["concern"],
    }
