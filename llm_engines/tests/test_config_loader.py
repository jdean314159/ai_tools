from __future__ import annotations

from pathlib import Path

import pytest

from llm_engines.contracts import EngineConfigError
from llm_engines.config_loader import (
    create_engine,
    ensure_user_config_exists,
    load_config,
    packaged_config_path,
)
from llm_engines.backends.mock import MockEngine


def test_packaged_config_exists() -> None:
    assert packaged_config_path().exists()


def test_load_packaged_config_contains_named_engines() -> None:
    config = load_config(packaged_config_path())
    assert "engines" in config
    assert "mock" in config["engines"]
    assert "qwen27b" in config["engines"]


def test_ensure_user_config_exists_copies_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    # user_config_path uses ~/.engram/llm_engines.yaml
    target = Path(str(home)) / ".engram" / "llm_engines.yaml"
    assert not target.exists()
    created = ensure_user_config_exists()
    assert created.exists()
    assert created.read_text(encoding="utf-8") == packaged_config_path().read_text(encoding="utf-8")


def test_load_config_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "custom.yaml"
    cfg.write_text(
        """engines:
  only_mock:
    backend: mock
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_ENGINES_CONFIG", str(cfg))
    loaded = load_config()
    assert "only_mock" in loaded["engines"]


def test_create_engine_named_config_returns_mock(tmp_path: Path) -> None:
    cfg = tmp_path / "engines.yaml"
    cfg.write_text(
        """engines:
  my_mock:
    backend: mock
    model: unit-test
""",
        encoding="utf-8",
    )
    engine = create_engine("my_mock", config_path=cfg)
    assert isinstance(engine, MockEngine)


def test_create_engine_unknown_name_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "engines.yaml"
    cfg.write_text("engines: {}\n", encoding="utf-8")
    with pytest.raises(EngineConfigError):
        create_engine("missing", config_path=cfg)


def test_create_engine_allows_override(tmp_path: Path) -> None:
    cfg = tmp_path / "engines.yaml"
    cfg.write_text(
        """engines:
  my_mock:
    backend: mock
    model: initial
""",
        encoding="utf-8",
    )
    engine = create_engine(
        "my_mock",
        config_path=cfg,
        engine_config_override={"model": "override-model"},
    )
    assert isinstance(engine, MockEngine)
    assert engine.model == "override-model"


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("engines: [", encoding="utf-8")
    with pytest.raises(EngineConfigError):
        load_config(cfg)
