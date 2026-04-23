"""
llm_engines/factory.py

EngineFactory: construct engines and failover profiles from config.

Supports two YAML formats:

1. Single engine (minimal):
       backend: ollama
       model: qwen3:27b
       options:
         keep_alive: 0

2. Multi-engine profile (from Engram's llm_engines.yaml):
       engines:
         qwen27b:
           type: ollama
           model: qwen3:27b
           base_url: http://localhost:11434
           num_gpu: null
           max_context: 32768
         qwen8b:
           type: ollama
           model: qwen3:8b
       profiles:
         default_local:
           engines: [qwen27b, qwen8b]
           allow_cloud_failover: false
           max_attempts: 4
           circuit_breaker_failures: 3
           circuit_breaker_cooldown_s: 30

Config resolution order (matching Engram):
  1. Explicit path argument
  2. ~/.engram/llm_engines.yaml  (user config)
  3. llm_engines/data/llm_engines.yaml  (packaged default)
"""
from __future__ import annotations

import importlib
import logging
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from llm_engines.contracts import (
    ChatModel,
    EngineConfigError,
)
from llm_engines.router import FailoverEngine, FailoverPolicy

logger = logging.getLogger(__name__)

_PACKAGED_DEFAULT = Path(__file__).parent / "data" / "llm_engines.yaml"
_USER_CONFIG = Path("~/.engram/llm_engines.yaml").expanduser()

# Lazy-import map: backend name → dotted class path
_BACKEND_MAP: dict[str, str] = {
    "ollama":    "llm_engines.backends.ollama.OllamaEngine",
    "anthropic": "llm_engines.backends.anthropic.AnthropicEngine",
    "openai":    "llm_engines.backends.openai.OpenAIEngine",
    "vllm":      "llm_engines.backends.vllm.vLLMEngine",
    "llamacpp":  "llm_engines.backends.llamacpp.LlamaCppEngine",
    "llama_cpp": "llm_engines.backends.llamacpp.LlamaCppEngine",
    "mock":      "llm_engines.backends.mock.MockEngine",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_class(dotted: str) -> type:
    module_path, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML config. Resolution: explicit → user → packaged default."""
    if config_path:
        path = Path(config_path).expanduser()
    elif _USER_CONFIG.exists():
        path = _USER_CONFIG
    elif _PACKAGED_DEFAULT.exists():
        path = _PACKAGED_DEFAULT
    else:
        return {}

    if not path.exists():
        raise EngineConfigError(f"Config file not found: {path}")

    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise EngineConfigError(f"Invalid YAML in {path}: {e}") from e


def _ensure_user_config() -> Path:
    """Copy packaged default to ~/.engram/ if no user config exists."""
    if not _USER_CONFIG.exists() and _PACKAGED_DEFAULT.exists():
        _USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_PACKAGED_DEFAULT, _USER_CONFIG)
    return _USER_CONFIG


# ---------------------------------------------------------------------------
# Single-engine construction
# ---------------------------------------------------------------------------

def _engine_from_config_dict(
    engine_cfg: dict[str, Any],
    engine_name: str = "<inline>",
) -> ChatModel:
    """
    Build one engine from a config dict.

    Accepts both flat format (backend/model keys) and named-engine format
    (type/model keys, matching Engram's llm_engines.yaml).
    """
    # Normalise key names
    backend = engine_cfg.get("type") or engine_cfg.get("backend")
    if not backend:
        raise EngineConfigError(
            f"Engine '{engine_name}' must specify 'type' (or 'backend')."
        )
    backend = backend.lower()

    if backend not in _BACKEND_MAP:
        raise EngineConfigError(
            f"Unknown backend '{backend}' in engine '{engine_name}'. "
            f"Available: {sorted(_BACKEND_MAP)}"
        )

    try:
        engine_cls = _import_class(_BACKEND_MAP[backend])
    except ImportError as e:
        raise EngineConfigError(
            f"Backend '{backend}' is not installed. "
            f"Install with: pip install llm-engines[{backend}]"
        ) from e

    # Build kwargs from config, passing only what the constructor accepts
    kwargs: dict[str, Any] = {}

    model = engine_cfg.get("model")
    if model:
        kwargs["model"] = model

    # Ollama-specific
    if backend == "ollama":
        if "base_url" in engine_cfg:
            kwargs["host"] = engine_cfg["base_url"].rstrip("/v1").rstrip("/")
        if "num_gpu" in engine_cfg and engine_cfg["num_gpu"] is not None:
            kwargs["num_gpu"] = int(engine_cfg["num_gpu"])
        if "thinking" in engine_cfg:
            kwargs["think"] = bool(engine_cfg["thinking"])
        if "keep_alive" in engine_cfg:
            kwargs["keep_alive"] = int(engine_cfg["keep_alive"])
        if bool(engine_cfg.get("auto_pull", False)):
            kwargs["auto_pull"] = True

    # Cloud engines
    if backend in ("anthropic", "openai"):
        api_key_env = engine_cfg.get("api_key_env")
        if api_key_env:
            kwargs["api_key"] = os.getenv(api_key_env)
        elif "api_key" in engine_cfg:
            kwargs["api_key"] = engine_cfg["api_key"]
        if "base_url" in engine_cfg:
            kwargs["base_url"] = engine_cfg["base_url"]
        if "is_cloud" in engine_cfg:
            kwargs["is_cloud"] = bool(engine_cfg["is_cloud"])

    # llama.cpp
    if backend in ("llamacpp", "llama_cpp"):
        if "base_url" in engine_cfg:
            kwargs["base_url"] = engine_cfg["base_url"]
        if "gguf_path" in engine_cfg:
            kwargs["gguf_path"] = engine_cfg["gguf_path"]
        if "n_gpu_layers" in engine_cfg:
            kwargs["n_gpu_layers"] = int(engine_cfg["n_gpu_layers"])

    # Pass-through options
    options = engine_cfg.get("options", {})
    if options:
        kwargs["options"] = options

    try:
        return engine_cls(**kwargs)
    except TypeError as e:
        raise EngineConfigError(
            f"Invalid arguments for backend '{backend}' in engine '{engine_name}': {e}"
        ) from e


# ---------------------------------------------------------------------------
# EngineFactory
# ---------------------------------------------------------------------------

class EngineFactory:
    """
    Create engine instances from config.

    Three usage patterns:

    1. Programmatic single engine:
           engine = EngineFactory.create("ollama", model="qwen3:8b")

    2. From simple YAML file:
           engine = EngineFactory.from_config("myconfig.yaml")

    3. From Engram-format YAML profile:
           engine = EngineFactory.from_profile("default_local", "llm_engines.yaml")
    """

    @classmethod
    def _import_backend(cls, backend: str) -> type:
        """Import and return the engine class for a backend name."""
        backend = backend.lower()
        if backend not in _BACKEND_MAP:
            raise EngineConfigError(
                f"Unknown backend '{backend}'. "
                f"Available: {sorted(_BACKEND_MAP)}"
            )
        return _import_class(_BACKEND_MAP[backend])

    @classmethod
    def create(cls, backend: str, **kwargs: Any) -> ChatModel:
        """
        Instantiate a single engine by backend name.

        Args:
            backend: "ollama" | "anthropic" | "openai" | "vllm" |
                     "llamacpp" | "mock"
            **kwargs: Passed to the engine constructor.

        Raises:
            EngineConfigError
        """
        cfg = {"type": backend, **kwargs}
        return _engine_from_config_dict(cfg, backend)

    @classmethod
    def from_config(cls, config_path: str | Path) -> ChatModel:
        """
        Build a single engine from a simple YAML file.

        YAML format:
            backend: ollama      # or 'type: ollama'
            model: qwen3:8b
            options:
              keep_alive: 0
        """
        config = _load_config(config_path)

        # Simple flat format: has 'backend' or 'type' at top level
        if "backend" in config or "type" in config:
            return _engine_from_config_dict(config, str(config_path))

        raise EngineConfigError(
            f"{config_path}: expected top-level 'backend'/'type' key for single-engine "
            "format, or use from_profile() for multi-engine YAML."
        )

    @classmethod
    def from_profile(
        cls,
        profile_name: str = "default_local",
        config_path: str | Path | None = None,
        override_engines: list[str] | None = None,
        override_allow_cloud: bool | None = None,
    ) -> FailoverEngine:
        """
        Build a FailoverEngine from a named profile in a YAML config.

        Args:
            profile_name:         Key in the 'profiles' section.
            config_path:          Optional explicit path. Falls back to
                                  ~/.engram/llm_engines.yaml, then packaged default.
            override_engines:     Replace the engine list from the profile.
            override_allow_cloud: Override allow_cloud_failover.

        Returns:
            FailoverEngine (implements ChatModel).

        Raises:
            EngineConfigError
        """
        config = _load_config(config_path)

        profiles = config.get("profiles") or {}
        if profile_name not in profiles:
            available = sorted(profiles)
            raise EngineConfigError(
                f"Profile '{profile_name}' not found. Available: {available}"
            )

        profile = profiles[profile_name] or {}
        engines_cfg = config.get("engines") or {}

        engine_names: list[str] = override_engines or list(profile.get("engines") or [])
        if not engine_names:
            raise EngineConfigError(
                f"Profile '{profile_name}' must list at least one engine."
            )

        engines: list[ChatModel] = []
        for name in engine_names:
            if name not in engines_cfg:
                available = sorted(engines_cfg)
                raise EngineConfigError(
                    f"Engine '{name}' (referenced in profile '{profile_name}') "
                    f"not found in 'engines' section. Available: {available}"
                )
            engine = _engine_from_config_dict(engines_cfg[name], name)
            engines.append(engine)
            logger.debug("Loaded engine '%s' for profile '%s'", name, profile_name)

        allow_cloud = (
            override_allow_cloud
            if override_allow_cloud is not None
            else bool(profile.get("allow_cloud_failover", False))
        )
        policy = FailoverPolicy(
            max_attempts=int(profile.get("max_attempts", 4)),
            allow_cloud_failover=allow_cloud,
            cloud_policy=str(profile.get("cloud_policy", "query_plus_summary")),
            circuit_breaker_failures=int(profile.get("circuit_breaker_failures", 3)),
            circuit_breaker_cooldown_s=float(
                profile.get("circuit_breaker_cooldown_s", 30.0)
            ),
        )
        return FailoverEngine(engines=engines, policy=policy, name=profile_name)

    @classmethod
    def from_engine_name(
        cls,
        engine_name: str,
        config_path: str | Path | None = None,
    ) -> ChatModel:
        """
        Build a single engine by its named entry in the 'engines' section.

        Compatible with Engram's create_engine() calling convention.
        """
        config = _load_config(config_path)
        engines_cfg = config.get("engines") or {}
        if engine_name not in engines_cfg:
            available = sorted(engines_cfg)
            raise EngineConfigError(
                f"Engine '{engine_name}' not found. Available: {available}"
            )
        return _engine_from_config_dict(engines_cfg[engine_name], engine_name)

    @classmethod
    def register_backend(cls, name: str, dotted_class_path: str) -> None:
        """Register a custom backend for use in create() and YAML configs."""
        _BACKEND_MAP[name.lower()] = dotted_class_path
