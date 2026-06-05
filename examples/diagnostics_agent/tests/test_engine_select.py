from __future__ import annotations

import pytest

from diagnostics_agent.engine_guard import require_local_engine
from diagnostics_agent.engine_select import (
    DIAGNOSTICS_POLICY,
    EngineChoice,
    build_engine,
    build_single_engine,
)
from diagnostics_agent.errors import RemoteEngineRefused
from llm_engines import FailoverEngine
from llm_engines.contracts import EngineCapabilities


def test_build_single_engine_uses_public_factory_for_ollama(monkeypatch) -> None:
    calls = []

    def fake_get_engine(backend, model, **kwargs):
        calls.append((backend, model, kwargs))
        return _FakeEngine(backend)

    monkeypatch.setattr("diagnostics_agent.engine_select.get_engine", fake_get_engine)

    engine = build_single_engine(EngineChoice("ollama", "qwen3:8b", base_url="http://host:11434"))

    assert isinstance(engine, _FakeEngine)
    assert calls == [("ollama", "qwen3:8b", {"base_url": "http://host:11434"})]


def test_build_single_engine_passes_llamacpp_knobs(monkeypatch) -> None:
    calls = []

    def fake_get_engine(backend, model, **kwargs):
        calls.append((backend, model, kwargs))
        return _FakeEngine(backend)

    monkeypatch.setattr("diagnostics_agent.engine_select.get_engine", fake_get_engine)

    build_single_engine(
        EngineChoice(
            "llamacpp",
            "/models/qwen.gguf",
            n_gpu_layers=-1,
            n_ctx=8192,
            n_batch=128,
            cache_type_k="q8_0",
            cache_type_v="q8_0",
            flash_attn=True,
            think=False,
        )
    )

    assert calls == [
        (
            "llamacpp",
            "/models/qwen.gguf",
            {
                "n_gpu_layers": -1,
                "n_ctx": 8192,
                "n_batch": 128,
                "cache_type_k": "q8_0",
                "cache_type_v": "q8_0",
                "flash_attn": True,
                "think": False,
            },
        )
    ]


def test_build_single_engine_passes_llamacpp_kv_cache_types(monkeypatch) -> None:
    calls = []

    def fake_get_engine(backend, model, **kwargs):
        calls.append((backend, model, kwargs))
        return _FakeEngine(backend)

    monkeypatch.setattr("diagnostics_agent.engine_select.get_engine", fake_get_engine)

    build_single_engine(
        EngineChoice(
            "llamacpp",
            "/models/qwen.gguf",
            cache_type_k="q8_0",
            cache_type_v="f16",
        )
    )

    assert calls == [
        (
            "llamacpp",
            "/models/qwen.gguf",
            {"cache_type_k": "q8_0", "cache_type_v": "f16", "think": True},
        )
    ]


def test_build_single_engine_passes_think_false_to_llamacpp(monkeypatch) -> None:
    calls = []

    def fake_get_engine(backend, model, **kwargs):
        calls.append(kwargs)
        return _FakeEngine(backend)

    monkeypatch.setattr("diagnostics_agent.engine_select.get_engine", fake_get_engine)
    build_single_engine(EngineChoice("llamacpp", "/models/qwen.gguf", think=False))
    assert calls[0]["think"] is False


def test_build_engine_wraps_fallback_with_local_only_policy(monkeypatch) -> None:
    def fake_get_engine(backend, model, **kwargs):
        return _FakeEngine(backend)

    monkeypatch.setattr("diagnostics_agent.engine_select.get_engine", fake_get_engine)
    choice = EngineChoice(
        "llamacpp",
        "/models/qwen.gguf",
        fallback=EngineChoice("ollama", "qwen3:8b", base_url="http://workstation:11434"),
    )

    engine = build_engine(choice)

    assert isinstance(engine, FailoverEngine)
    assert engine.policy == DIAGNOSTICS_POLICY
    assert engine.policy.allow_cloud_failover is False
    assert engine.policy.reduce_output_on_oom is True
    require_local_engine(engine)


def test_build_engine_rejects_cloud_member_before_wrapping(monkeypatch) -> None:
    def fake_get_engine(backend, model, **kwargs):
        return _FakeEngine("openai", is_cloud=True)

    monkeypatch.setattr("diagnostics_agent.engine_select.get_engine", fake_get_engine)

    with pytest.raises(RemoteEngineRefused):
        build_engine(EngineChoice("ollama", "qwen3:8b"))


class _FakeEngine:
    def __init__(self, backend: str, *, is_cloud: bool = False) -> None:
        self.backend = backend
        self.is_cloud = is_cloud

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(chat=True)
