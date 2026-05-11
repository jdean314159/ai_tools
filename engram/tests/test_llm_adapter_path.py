"""Regression test for the llm_adapter path through ProjectMemory.respond().

Verifies that ProjectMemory accepts an llm_adapter (preferred new path) in
addition to llm_engine (legacy path), and that respond() correctly routes
through whichever is provided.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


class _FakeEngineWithKwargs:
    """Mimics an llm_engines.ChatModel-style engine (only the attributes used)."""

    model_name = "fake-1b"
    backend = "fake"

    def __init__(self):
        self.calls = []

    def get_capabilities(self):
        from llm_engines.contracts import EngineCapabilities
        return EngineCapabilities(chat=True, embeddings=False)

    def generate(self, request):
        from llm_engines.contracts import GenerationResponse, ChatMessage
        self.calls.append(request)
        return GenerationResponse(
            message=ChatMessage(role="assistant", content="adapter-path response"),
            model_name=self.model_name,
            backend=self.backend,
        )


def _project_memory_factory(tmp_path, **pm_kwargs):
    from engram import ProjectMemory
    from engram.memory.types import ProjectType
    return ProjectMemory(
        project_id="test-proj",
        project_type=ProjectType.GENERAL_ASSISTANT,
        base_dir=tmp_path / "pm",
        session_id="test",
        **pm_kwargs,
    )


def test_respond_uses_llm_adapter_when_provided(tmp_path):
    """When llm_adapter= is passed, respond() routes through it, not llm_engine."""
    from engram.adapters.llm_adapter import EngramLLMAdapter

    fake = _FakeEngineWithKwargs()
    adapter = EngramLLMAdapter(fake)
    pm = _project_memory_factory(tmp_path, llm_adapter=adapter)

    out = pm.respond("Hello there.")

    assert out["answer"] == "adapter-path response"
    assert len(fake.calls) >= 1, "Adapter should have called the underlying engine"
    pm.close()


def test_respond_raises_when_neither_llm_provided(tmp_path):
    """ProjectMemory without an LLM should raise on respond()."""
    pm = _project_memory_factory(tmp_path)
    with pytest.raises(RuntimeError, match="requires an LLM"):
        pm.respond("Hello there.")
    pm.close()


def test_fingerprint_unwraps_adapter(tmp_path):
    """resolve_neural_fingerprint should walk into adapter.engine for the model name."""
    from engram.adapters.llm_adapter import EngramLLMAdapter
    from engram.memory.neural_coordinator import resolve_neural_fingerprint

    fake = _FakeEngineWithKwargs()
    adapter = EngramLLMAdapter(fake)

    # Both should produce the same fingerprint
    assert resolve_neural_fingerprint(adapter) == "fake-1b"
    assert resolve_neural_fingerprint(fake) == "fake-1b"
