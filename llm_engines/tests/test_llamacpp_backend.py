from __future__ import annotations

import importlib
import sys
import types

from llm_engines.contracts import ChatMessage, GenerationRequest


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
        "type": "json_schema",
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


def test_llamacpp_reports_structured_output_capability(monkeypatch) -> None:
    module = _load_llamacpp_with_fake_dependency(monkeypatch)
    engine = module.LlamaCppEngine(model_path="/models/test.gguf")

    assert engine.get_capabilities().structured_output is True


def _load_llamacpp_with_fake_dependency(monkeypatch):
    fake_module = types.ModuleType("llama_cpp")
    fake_module.Llama = _FakeLlama
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_module)
    sys.modules.pop("llm_engines.backends.llamacpp", None)
    return importlib.import_module("llm_engines.backends.llamacpp")


class _FakeLlama:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.calls: list[dict] = []

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
