"""
engine_registry_bootstrap.py

Connects llm_inspector_ui's EngineService to the llm_engines package.

Two components:

1. ChatModelAdapter — wraps a llm_engines ChatModel to expose the invoke()
   signature the orchestrator expects (prompt str → EngineResponse). This is
   the contract bridge between the old EngineHandle protocol and ChatModel.generate().

2. LlmEnginesRegistry — implements the EngineRegistry protocol using
   llm_engines config_loader and EngineFactory. Returns ChatModelAdapter
   instances from create_engine().

3. bootstrap_llm_engines_registry() — builds the real registry if llm_engines
   is importable, otherwise returns NullRegistry so the UI degrades gracefully.
"""

from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# NullRegistry — graceful degradation when llm_engines is not importable
# ---------------------------------------------------------------------------


class NullRegistry:
    def list_engines(self):
        return []

    def list_models(self, engine_id: str):
        return []

    def search_models(self, query: str, source: str | None = None):
        return []

    def provision_model(self, request):
        raise RuntimeError("No llm_engines registry is configured.")

    def create_engine(self, engine_id: str, config: dict[str, Any] | None = None):
        raise RuntimeError("No llm_engines registry is configured.")


# ---------------------------------------------------------------------------
# ChatModelAdapter — bridges ChatModel.generate() → invoke() contract
# ---------------------------------------------------------------------------


class ChatModelAdapter:
    """Wraps a llm_engines ChatModel to match the EngineHandle.invoke() signature.

    The orchestrator calls:
        engine.invoke(prompt=str, model_id=str, settings=dict, session_id=str)
        → EngineResponse(text=str, metrics=dict)

    ChatModel.generate() expects GenerationRequest and returns GenerationResponse.
    This adapter translates between the two.
    """

    def __init__(self, engine: Any, engine_id: str) -> None:
        self._engine = engine
        self._engine_id = engine_id

    def invoke(
        self,
        *,
        prompt: str,
        model_id: Optional[str] = None,
        settings: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Any:
        """Translate to ChatModel.generate() and return EngineResponse."""
        from llm_engines.contracts import ChatMessage, GenerationRequest
        from llm_inspector_ui.services.engine_service import EngineResponse

        settings = settings or {}
        max_tokens = int(settings.get("max_tokens", 2048))
        temperature = float(settings.get("temperature", 0.7))
        system_prompt = settings.get("system_prompt", "")

        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))

        request = GenerationRequest(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            response = self._engine.generate(request)
            text = response.message.content or ""
            metrics = {
                "engine": self._engine_id,
                "model_id": model_id or self._engine_id,
                "session_id": session_id,
                "prompt_chars": len(prompt),
                "output_chars": len(text),
            }
            # Include token counts if the response carries them
            if hasattr(response, "usage") and response.usage:
                metrics["prompt_tokens"] = getattr(response.usage, "prompt_tokens", None)
                metrics["completion_tokens"] = getattr(response.usage, "completion_tokens", None)
        except Exception as exc:
            # Return the error as text so the UI surfaces it rather than crashing
            text = f"[Engine error: {exc}]"
            metrics = {
                "engine": self._engine_id,
                "error": str(exc),
            }

        return EngineResponse(text=text, metrics=metrics)


# ---------------------------------------------------------------------------
# LlmEnginesRegistry — EngineRegistry protocol backed by llm_engines config
# ---------------------------------------------------------------------------


class LlmEnginesRegistry:
    """Implements the EngineRegistry protocol using llm_engines config_loader.

    Reads engine definitions from the YAML config (default: ~/.engram/llm_engines.yaml)
    and creates ChatModel instances via EngineFactory on demand.
    """

    def __init__(self) -> None:
        from llm_engines.config_loader import load_config
        from llm_engines.contracts import EngineDescriptor, ModelDescriptor

        self._config = load_config()
        self._EngineDescriptor = EngineDescriptor
        self._ModelDescriptor = ModelDescriptor

    def list_engines(self) -> list[Any]:
        engines_cfg = self._config.get("engines") or {}
        result = []
        for name, cfg in engines_cfg.items():
            cfg = cfg or {}
            backend = cfg.get("backend") or cfg.get("type", "unknown")
            label = f"{name} ({backend})"
            is_local = backend in ("ollama", "llama_cpp", "vllm")
            try:
                # llm_engines.contracts.EngineDescriptor fields:
                # engine_id, label, local, supports_chat, supports_streaming,
                # supports_tools, supports_vision, metadata
                result.append(
                    self._EngineDescriptor(
                        engine_id=name,
                        label=label,
                        local=is_local,
                        metadata={"backend": backend},
                    )
                )
            except Exception:
                pass
        return result

    def health_check(self, engine_id: str) -> dict:
        """Probe engine reachability. Called by _probe_engine_reachability()."""
        engines_cfg = self._config.get("engines") or {}
        cfg = engines_cfg.get(engine_id) or {}
        backend = cfg.get("backend") or cfg.get("type", "")

        if backend == "ollama":
            try:
                from llm_engines.discovery import check_ollama_running

                base_url = cfg.get("base_url", "http://localhost:11434")
                running = check_ollama_running(base_url)
                return {
                    "reachable": running,
                    "message": "Ollama is running." if running else "Ollama is not reachable.",
                }
            except Exception as exc:
                return {"reachable": False, "message": f"Health check failed: {exc}"}

        if backend == "llama_cpp":
            # llama_cpp engines are process-based; treat as reachable if configured
            return {"reachable": True, "message": "llama.cpp engine configured."}

        if backend in ("anthropic", "openai"):
            import os

            key_var = "ANTHROPIC_API_KEY" if backend == "anthropic" else "OPENAI_API_KEY"
            has_key = bool(os.environ.get(key_var))
            return {
                "reachable": has_key,
                "message": f"{key_var} {'set' if has_key else 'not set'} in environment.",
            }

        return {"reachable": None, "message": "No health probe for this backend."}

    def list_models(self, engine_id: str) -> list[Any]:
        """List available models for an engine."""
        engines_cfg = self._config.get("engines") or {}
        cfg = engines_cfg.get(engine_id) or {}
        backend = cfg.get("backend") or cfg.get("type", "")

        if backend == "ollama":
            try:
                from llm_engines.discovery import list_ollama_models

                base_url = cfg.get("base_url", "http://localhost:11434")
                models = list_ollama_models(base_url)
                return [self._coerce_model_descriptor(m.name, engine_id) for m in models]
            except Exception:
                pass

        # Fallback: return the configured model as the only option
        model = cfg.get("model")
        if model:
            return [self._coerce_model_descriptor(model, engine_id)]

        return []

    def _coerce_model_descriptor(self, model_id: str, engine_id: str) -> Any:
        """Build a ModelDescriptor using only fields the dataclass actually has."""
        # ModelDescriptor fields: model_id, label, source, installed
        # (from llm_inspector_ui.services.engine_service)
        # We use whatever fields exist, falling back gracefully.
        try:
            return self._ModelDescriptor(
                model_id=model_id,
                label=model_id,
                source=engine_id,
                installed=True,
            )
        except TypeError:
            pass
        # Minimal fallback if field names differ
        try:
            return self._ModelDescriptor(model_id=model_id, label=model_id)
        except TypeError:
            return self._ModelDescriptor(model_id=model_id)

    def search_models(
        self,
        query: str,
        source: str | None = None,
    ) -> list[Any]:
        """Search across all engines for models matching query."""
        results = []
        for descriptor in self.list_engines():
            for model in self.list_models(descriptor.engine_id):
                if query.lower() in model.model_id.lower():
                    results.append(model)
        return results

    def provision_model(self, request: Any) -> Any:
        """Pull an Ollama model if it's not already available."""
        try:
            from llm_engines.discovery import pull_ollama_model
            from llm_engines.contracts import ProvisionResult

            engine_id = getattr(request, "engine_id", "")
            model_id = getattr(request, "model_id", "")
            engines_cfg = self._config.get("engines") or {}
            cfg = engines_cfg.get(engine_id) or {}
            base_url = cfg.get("base_url", "http://localhost:11434")
            success = pull_ollama_model(model_id, base_url=base_url)
            return ProvisionResult(
                engine_id=engine_id,
                model_id=model_id,
                local_ref=model_id if success else None,
                message="Pull complete." if success else f"Failed to pull {model_id}.",
            )
        except Exception as exc:
            try:
                from llm_engines.contracts import ProvisionResult

                return ProvisionResult(
                    engine_id="",
                    model_id="",
                    local_ref=None,
                    message=f"Provision error: {exc}",
                )
            except Exception:
                raise

    def create_engine(
        self,
        engine_id: str,
        config: dict[str, Any] | None = None,
    ) -> ChatModelAdapter:
        """Create a ChatModelAdapter for the named engine."""
        from llm_engines.config_loader import create_engine as cfg_create_engine

        engine_config_override = config or {}
        chat_model = cfg_create_engine(
            engine_id,
            engine_config_override=engine_config_override if engine_config_override else None,
        )
        return ChatModelAdapter(engine=chat_model, engine_id=engine_id)


# ---------------------------------------------------------------------------
# bootstrap_llm_engines_registry — called once at app startup
# ---------------------------------------------------------------------------


def bootstrap_llm_engines_registry() -> Any:
    """Build and return the real registry, or NullRegistry on failure.

    Called by app.py:
        st.session_state.engine_service = EngineService(registry=get_engine_registry())
    """
    try:
        registry = LlmEnginesRegistry()
        # Smoke-test: can we at least list engines without crashing?
        _ = registry.list_engines()
        return registry
    except ImportError:
        # llm_engines not installed in this environment
        return NullRegistry()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to build LlmEnginesRegistry: %s. Falling back to NullRegistry.", exc
        )
        return NullRegistry()
