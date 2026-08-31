"""
test_engine_load_failures.py

Negative-path tests for EngineManager._load_engine().

All engine loading now goes through llm_engines / LLMEnginesAdapter.
Tests cover:
  - USE_LEGACY_ENGINE=1 raises the deprecation error
  - Unknown engine type raises RuntimeError
  - Missing API keys (anthropic, gemini, openai) raise RuntimeError
  - build_engine connection failure raises RuntimeError
"""

from __future__ import annotations

import copy
import pytest

from language_tutor.engine_manager import EngineManager
from language_tutor.hardware_strategy import STRATEGIES


@pytest.fixture
def manager() -> EngineManager:
    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    return EngineManager(strategy)


# ---------------------------------------------------------------------------
# USE_LEGACY_ENGINE deprecation guard
# ---------------------------------------------------------------------------


def test_use_legacy_engine_raises_deprecation_error(manager, monkeypatch):
    monkeypatch.setenv("USE_LEGACY_ENGINE", "1")
    with pytest.raises(RuntimeError, match="USE_LEGACY_ENGINE is no longer supported"):
        manager._load_engine({"engine": "ollama", "model": "any"}, "execution")


# ---------------------------------------------------------------------------
# Unknown engine type
# ---------------------------------------------------------------------------


def test_unknown_engine_type_raises_runtime_error(manager, monkeypatch):
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)

    def _fail(config):
        raise ValueError(f"Unknown engine type '{config['engine']}'")

    monkeypatch.setattr("language_tutor.llm_engines_adapter.build_engine", _fail)
    with pytest.raises(RuntimeError, match="Cannot initialize"):
        manager._load_engine({"engine": "banana", "model": "banana-7b"}, "planning")


# ---------------------------------------------------------------------------
# API-key failures (build_engine propagates RuntimeError)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_var,engine_type,match",
    [
        ("ANTHROPIC_API_KEY", "anthropic", "Cannot initialize"),
        ("GOOGLE_API_KEY", "gemini", "Cannot initialize"),
        ("OPENAI_API_KEY", "openai", "Cannot initialize"),
    ],
)
def test_missing_api_key_raises_runtime_error(manager, monkeypatch, env_var, engine_type, match):
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)
    monkeypatch.delenv(env_var, raising=False)

    def _fail(config):
        raise RuntimeError(f"{env_var} not set")

    monkeypatch.setattr("language_tutor.llm_engines_adapter.build_engine", _fail)
    with pytest.raises(RuntimeError, match=match):
        manager._load_engine({"engine": engine_type, "model": "model-x"}, "planning")


# ---------------------------------------------------------------------------
# Connection / server-not-running failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine_type", ["ollama", "vllm", "llama_cpp"])
def test_server_not_running_raises_runtime_error(manager, monkeypatch, engine_type):
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)

    def _fail(config):
        raise OSError(f"Connection refused — {config['engine']} server not running")

    monkeypatch.setattr("language_tutor.llm_engines_adapter.build_engine", _fail)
    with pytest.raises(RuntimeError, match="Cannot initialize"):
        manager._load_engine({"engine": engine_type, "model": "model-x"}, "execution")


# ---------------------------------------------------------------------------
# Successful load path (sanity)
# ---------------------------------------------------------------------------


def test_successful_load_returns_adapter(manager, monkeypatch):
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)

    class _FakeAdapter:
        model_name = "fake"

    monkeypatch.setattr(
        "language_tutor.llm_engines_adapter.build_engine", lambda cfg: _FakeAdapter()
    )
    engine = manager._load_engine({"engine": "ollama", "model": "fake"}, "execution")
    assert engine.model_name == "fake"


# ---------------------------------------------------------------------------
# EngineManager.get_executor / get_planner use _load_engine
# ---------------------------------------------------------------------------


def test_get_executor_calls_load_engine(monkeypatch):
    called = []
    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    mgr = EngineManager(strategy)

    class _FakeAdapter:
        model_name = "fake-executor"

    def _fake_load(self, config, purpose):
        called.append(purpose)
        return _FakeAdapter()

    monkeypatch.setattr(EngineManager, "_load_engine", _fake_load)
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)

    executor = mgr.get_executor()
    assert executor.model_name == "fake-executor"
    assert "execution" in called


def test_get_planner_calls_load_engine(monkeypatch):
    called = []
    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    mgr = EngineManager(strategy)

    class _FakeAdapter:
        model_name = "fake-planner"

    def _fake_load(self, config, purpose):
        called.append(purpose)
        return _FakeAdapter()

    monkeypatch.setattr(EngineManager, "_load_engine", _fake_load)
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)

    planner = mgr.get_planner()
    assert planner.model_name == "fake-planner"
    assert "planning" in called
