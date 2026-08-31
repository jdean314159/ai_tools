"""
tests/test_factory.py

EngineFactory tests. Single-engine and profile construction.
All tests that require live backends are marked @pytest.mark.ollama.
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from llm_engines.contracts import EngineConfigError
from llm_engines.backends.mock import MockEngine
from llm_engines.factory import EngineFactory
from llm_engines.router import FailoverEngine


class TestCreateSingleEngine:
    def test_create_mock(self) -> None:
        engine = EngineFactory.create("mock", model="test-model")
        assert isinstance(engine, MockEngine)

    def test_create_unknown_backend_raises(self) -> None:
        with pytest.raises(EngineConfigError, match="Unknown backend"):
            EngineFactory.create("nonexistent_backend", model="foo")

    def test_register_custom_backend(self) -> None:
        EngineFactory.register_backend("custom_mock", "llm_engines.backends.mock.MockEngine")
        engine = EngineFactory.create("custom_mock", model="custom")
        assert isinstance(engine, MockEngine)

    def test_create_llamacpp_passes_kv_cache_types(self, monkeypatch) -> None:
        calls = []

        class FakeLlamaCppEngine:
            def __init__(self, **kwargs) -> None:
                calls.append(kwargs)

        monkeypatch.setattr(
            "llm_engines.factory._import_class",
            lambda _dotted: FakeLlamaCppEngine,
        )

        EngineFactory.create(
            "llamacpp",
            model="/models/qwen.gguf",
            n_gpu_layers="8",
            n_ctx="8192",
            n_batch="128",
            n_ubatch="64",
            cache_type_k="q8_0",
            cache_type_v="f16",
            flash_attn=True,
        )

        assert calls == [
            {
                "model_path": "/models/qwen.gguf",
                "n_gpu_layers": 8,
                "n_ctx": 8192,
                "n_batch": 128,
                "n_ubatch": 64,
                "cache_type_k": "q8_0",
                "cache_type_v": "f16",
                "flash_attn": True,
            }
        ]

    def test_create_vllm_preserves_remote_server_settings(self, monkeypatch) -> None:
        calls = []

        class FakeVLLMEngine:
            def __init__(self, **kwargs) -> None:
                calls.append(kwargs)

        monkeypatch.setattr(
            "llm_engines.factory._import_class",
            lambda _dotted: FakeVLLMEngine,
        )

        EngineFactory.create(
            "vllm",
            model="unsloth/Qwen3.8-27B-NVFP4",
            base_url="http://192.168.50.225:8000/v1",
            max_context="262144",
            timeout="120",
            debug=True,
        )

        assert calls == [
            {
                "model": "unsloth/Qwen3.8-27B-NVFP4",
                "base_url": "http://192.168.50.225:8000/v1",
                "max_context": 262144,
                "timeout": 120.0,
                "debug": True,
            }
        ]


class TestFromConfig:
    def test_simple_yaml_mock(self, tmp_path: Path) -> None:
        config = tmp_path / "engine.yaml"
        config.write_text("type: mock\nmodel: test-1b\n")
        engine = EngineFactory.from_config(config)
        assert isinstance(engine, MockEngine)

    def test_missing_config_raises(self) -> None:
        with pytest.raises(EngineConfigError, match="not found"):
            EngineFactory.from_config("/nonexistent/path.yaml")

    def test_multi_engine_yaml_raises_helpful_error(self, tmp_path: Path) -> None:
        config = tmp_path / "multi.yaml"
        config.write_text("engines:\n  mock:\n    type: mock\n    model: m\n")
        with pytest.raises(EngineConfigError, match="from_profile"):
            EngineFactory.from_config(config)


class TestFromProfile:
    def _write_profile_config(self, tmp_path: Path) -> Path:
        cfg = {
            "engines": {
                "primary": {"type": "mock", "model": "primary-model"},
                "secondary": {"type": "mock", "model": "secondary-model"},
            },
            "profiles": {
                "test_profile": {
                    "engines": ["primary", "secondary"],
                    "allow_cloud_failover": False,
                    "max_attempts": 4,
                    "circuit_breaker_failures": 3,
                    "circuit_breaker_cooldown_s": 30,
                }
            },
        }
        path = tmp_path / "llm_engines.yaml"
        path.write_text(yaml.dump(cfg))
        return path

    def test_from_profile_returns_failover_engine(self, tmp_path: Path) -> None:
        config = self._write_profile_config(tmp_path)
        engine = EngineFactory.from_profile("test_profile", config_path=config)
        assert isinstance(engine, FailoverEngine)
        assert len(engine.engines) == 2

    def test_profile_not_found_raises(self, tmp_path: Path) -> None:
        config = self._write_profile_config(tmp_path)
        with pytest.raises(EngineConfigError, match="not found"):
            EngineFactory.from_profile("nonexistent", config_path=config)

    def test_override_engines(self, tmp_path: Path) -> None:
        config = self._write_profile_config(tmp_path)
        engine = EngineFactory.from_profile(
            "test_profile",
            config_path=config,
            override_engines=["primary"],
        )
        assert len(engine.engines) == 1

    def test_from_engine_name(self, tmp_path: Path) -> None:
        config = self._write_profile_config(tmp_path)
        engine = EngineFactory.from_engine_name("primary", config_path=config)
        assert isinstance(engine, MockEngine)

    def test_unknown_engine_in_profile_raises(self, tmp_path: Path) -> None:
        config = self._write_profile_config(tmp_path)
        with pytest.raises(EngineConfigError, match="not found"):
            EngineFactory.from_profile(
                "test_profile",
                config_path=config,
                override_engines=["nonexistent_engine"],
            )
