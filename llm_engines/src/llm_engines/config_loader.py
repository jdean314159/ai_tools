"""Minimal config/bootstrap helpers extracted and normalized from Engram.

This module intentionally keeps only the v0.1-friendly pieces:
- packaged default config
- user config bootstrap
- YAML loading
- create engine by named config entry

It does not include failover profiles, routing, or telemetry.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, cast

import yaml

from llm_engines.contracts import ChatModel, EngineConfigError
from llm_engines.factory import EngineFactory

_DEFAULT_CONFIG = Path(__file__).resolve().parent / "data" / "llm_engines.yaml"


def packaged_config_path() -> Path:
    """Return the packaged default config path."""
    return _DEFAULT_CONFIG


def user_config_path() -> Path:
    """Return the default per-user config path.

    Uses ~/.engram/llm_engines.yaml to co-locate with Engram's config.
    Override via LLM_ENGINES_CONFIG env var.
    """
    return Path("~/.engram/llm_engines.yaml").expanduser()


def ensure_user_config_exists(path: str | Path | None = None) -> Path:
    """Ensure a user config exists by copying the packaged default if missing."""
    target = Path(path).expanduser() if path is not None else user_config_path()
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(packaged_config_path(), target)
    return target


def _resolve_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser()

    env_path = os.getenv("LLM_ENGINES_CONFIG")
    if env_path:
        return Path(env_path).expanduser()

    return ensure_user_config_exists()


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load config YAML.

    Resolution order:
    1) explicit config_path
    2) LLM_ENGINES_CONFIG env var
    3) user config (~/.llm_engines/engines.yaml), auto-created from packaged default
    4) packaged default
    """
    path = _resolve_config_path(config_path)
    if not path.exists():
        path = packaged_config_path()

    if not path.exists():
        raise EngineConfigError(f"Config file not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise EngineConfigError(f"Invalid YAML in {path}: {e}") from e

    return data or {}


def create_engine(
    engine_name: str,
    config_path: str | Path | None = None,
    engine_config_override: dict[str, Any] | None = None,
) -> ChatModel:
    """Create an engine from a named entry in the YAML config."""
    config = load_config(config_path)
    engines_cfg = config.get("engines") or {}
    if engine_name not in engines_cfg:
        available = ", ".join(sorted(engines_cfg)) or "(none)"
        raise EngineConfigError(
            f"Engine '{engine_name}' not found in config. Available: {available}"
        )

    entry = dict(engines_cfg[engine_name] or {})
    if engine_config_override:
        entry.update(engine_config_override)

    backend = entry.get("backend") or entry.get("type")
    if not backend:
        raise EngineConfigError(
            f"Engine '{engine_name}' must define 'backend' (or legacy 'type')."
        )

    model = entry.get("model")
    options = dict(entry.get("options") or {})

    reserved = {
        "backend", "type", "model", "options", "description",
        # Framework-level keys not passed to engine constructors
        "system_prompt", "compression_strategy", "max_retries",
        "launch", "telemetry", "tags", "notes",
        # Generation parameters (not constructor args)
        "max_tokens", "temperature", "context_size", "max_context",
    }
    passthrough = {k: v for k, v in entry.items() if k not in reserved}

    # Expand ~ in path values
    for key in ("model_path",):
        if key in passthrough and isinstance(passthrough[key], str):
            import os
            passthrough[key] = os.path.expanduser(passthrough[key])

    kwargs: dict[str, Any] = {**options, **passthrough}

    # LlamaCppEngine uses model_path, not model — don't pass model as a kwarg
    _backends_without_model = {"llama_cpp", "llamacpp"}
    if model is not None and str(backend).lower() not in _backends_without_model:
        kwargs["model"] = model

    # Call the constructor directly with our cleaned kwargs,
    # bypassing EngineFactory.create() which would remap keys via _engine_from_config_dict.
    try:
        engine_cls = EngineFactory._import_backend(str(backend))
        return cast(ChatModel, engine_cls(**kwargs))
    except ImportError as e:
        raise EngineConfigError(
            f"Backend '{backend}' is not installed. "
            f"Install with: pip install llm-engines[{backend}]"
        ) from e
    except TypeError as e:
        raise EngineConfigError(
            f"Invalid arguments for backend '{backend}': {e}"
        ) from e
