from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from llm_harness_core import CapabilityDescriptor, CapabilityKind
from llm_engines.contracts import (
    EngineDescriptor,
    ModelDescriptor,
    ProvisionRequest,
    ProvisionResult,
)


@dataclass
class EngineConfigField:
    name: str
    label: str
    field_type: str = "text"  # text | password | int | float | bool
    default: Any = None
    required: bool = False
    help: str = ""
    placeholder: str = ""


@dataclass
class EngineResponse:
    text: str
    metrics: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


@dataclass
class EngineHealth:
    engine_id: str
    label: str
    exists: bool
    reachable: Optional[bool]
    models_available: Optional[bool]
    model_count: Optional[int]
    status: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineRunReadiness:
    engine_id: str
    can_run: bool
    severity: str  # "ok" | "warning" | "error"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class EchoEngine:
    def invoke(
        self,
        *,
        prompt: str,
        model_id: Optional[str] = None,
        settings: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> EngineResponse:
        max_chars = int((settings or {}).get("echo_max_chars", 400))
        text = prompt[-max_chars:]
        return EngineResponse(
            text=text,
            metrics={
                "engine": "echo",
                "model_id": model_id or "echo",
                "session_id": session_id,
                "prompt_chars": len(prompt),
            },
        )


class EngineService:
    """
    Thin wrapper around llm_engines with graceful fallback.

    Today:
      - always exposes an 'echo' engine so the UI can run end-to-end
      - delegates to a registry when available
      - exposes readiness/health checks so the UI can distinguish:
          exists / reachable / models available
      - exposes config schema so the UI can render per-engine connection fields
    """

    def __init__(self, registry: Any | None = None):
        self.registry = registry

    def describe_engine_capability(
        self,
        engine_id: str,
        *,
        config: Optional[dict[str, Any]] = None,
    ) -> CapabilityDescriptor:
        if engine_id == "echo":
            return CapabilityDescriptor(
                kind=CapabilityKind.ENGINE,
                provider="llm_inspector_ui",
                component="EchoEngine",
                version="0.1.0",
                summary="Built-in debug engine for UI validation and smoke tests.",
                features=("debug_echo",),
                input_types=("prompt",),
                output_types=("text", "metrics"),
                metadata={"engine_id": "echo", "local": True},
            )

        descriptor = next((e for e in self.list_engines() if e.engine_id == engine_id), None)
        metadata = {"engine_id": engine_id}
        if descriptor is not None:
            metadata.update({"label": descriptor.label, "local": descriptor.local})

        try:
            from llm_engines import describe_engine as describe_llm_engine

            engine = self.create_engine(engine_id, config or {})
            capability = describe_llm_engine(engine)
            merged = dict(capability.metadata)
            merged.update(metadata)
            return CapabilityDescriptor(
                kind=capability.kind,
                provider=capability.provider,
                component=capability.component,
                version=capability.version,
                summary=capability.summary,
                features=capability.features,
                input_types=capability.input_types,
                output_types=capability.output_types,
                metadata=merged,
            )
        except Exception as exc:
            metadata["describe_error"] = f"{type(exc).__name__}: {exc}"
            return CapabilityDescriptor(
                kind=CapabilityKind.ENGINE,
                provider="llm_inspector_ui",
                component=(descriptor.label if descriptor is not None else engine_id),
                version="0.1.0",
                summary="Engine capability descriptor derived from registry metadata.",
                features=(),
                input_types=("prompt",),
                output_types=("text",),
                metadata=metadata,
            )

    def list_engine_capabilities(
        self, configs: Optional[dict[str, dict[str, Any]]] = None
    ) -> list[CapabilityDescriptor]:
        configs = configs or {}
        return [
            self.describe_engine_capability(
                engine.engine_id, config=configs.get(engine.engine_id, {})
            )
            for engine in self.list_engines()
        ]

    def get_run_readiness(
        self,
        engine_id: str,
        *,
        config: Optional[dict[str, Any]] = None,
        model_id: Optional[str] = None,
    ) -> EngineRunReadiness:
        if engine_id == "echo":
            return EngineRunReadiness(
                engine_id="echo",
                can_run=True,
                severity="ok",
                message="Echo engine is ready.",
                details={},
            )

        health = self.get_engine_health(engine_id, config=config or {})
        if not health.exists:
            return EngineRunReadiness(
                engine_id=engine_id,
                can_run=False,
                severity="error",
                message=health.message or "Engine is not registered.",
                details={"health": asdict(health)},
            )

        if health.reachable is False:
            return EngineRunReadiness(
                engine_id=engine_id,
                can_run=False,
                severity="error",
                message=health.message or "Engine is not reachable.",
                details={"health": asdict(health)},
            )

        models = self.list_models(engine_id, config=config or {})
        if not models:
            return EngineRunReadiness(
                engine_id=engine_id,
                can_run=False,
                severity="error",
                message="Engine is reachable but no models are available.",
                details={"health": asdict(health)},
            )

        if not model_id:
            return EngineRunReadiness(
                engine_id=engine_id,
                can_run=False,
                severity="error",
                message="Select a model before running.",
                details={"health": asdict(health)},
            )

        model_ids = {model.model_id for model in models}
        if model_id not in model_ids:
            return EngineRunReadiness(
                engine_id=engine_id,
                can_run=False,
                severity="error",
                message=f"Selected model '{model_id}' is not available for this engine/configuration.",
                details={
                    "health": asdict(health),
                    "available_models": sorted(model_ids),
                },
            )

        return EngineRunReadiness(
            engine_id=engine_id,
            can_run=True,
            severity="ok",
            message="Engine and model are ready.",
            details={"health": asdict(health)},
        )

    def list_engines(self) -> list[EngineDescriptor]:
        engines = [
            EngineDescriptor(engine_id="echo", label="Echo (debug)", local=True),
        ]
        if self.registry is None:
            return engines

        list_engines = getattr(self.registry, "list_engines", None)
        if not callable(list_engines):
            return engines

        try:
            for item in list_engines():
                engines.append(self._coerce_engine_descriptor(item))
        except Exception:
            return engines

        deduped: dict[str, EngineDescriptor] = {}
        for engine in engines:
            deduped[engine.engine_id] = engine
        return list(deduped.values())

    def get_engine_config_schema(self, engine_id: str) -> list[EngineConfigField]:
        if engine_id == "echo":
            return []

        if self.registry is not None:
            for method_name in ("get_engine_config_schema", "describe_engine"):
                method = getattr(self.registry, method_name, None)
                if not callable(method):
                    continue
                try:
                    result = method(engine_id)
                except Exception:
                    continue

                if method_name == "describe_engine" and isinstance(result, dict):
                    result = result.get("config_schema") or result.get("engine_config_schema") or []

                fields = self._coerce_config_schema(result)
                if fields:
                    return fields

        return self._heuristic_config_schema(engine_id)

    def list_models(
        self,
        engine_id: str,
        *,
        config: Optional[dict[str, Any]] = None,
    ) -> list[ModelDescriptor]:
        models, _ = self._list_models_with_error(engine_id, config=config)
        return models

    def search_models(self, query: str, *, source: str | None = None) -> list[ModelDescriptor]:
        if not query.strip() or self.registry is None:
            return []

        search_models = getattr(self.registry, "search_models", None)
        if not callable(search_models):
            return []

        try:
            results = search_models(query, source=source)
        except TypeError:
            try:
                results = search_models(query)
            except Exception:
                return []
        except Exception:
            return []

        return [
            self._coerce_model_descriptor(item, default_source=source or "search")
            for item in results
        ]

    def provision_model(
        self,
        *,
        source: str,
        model_id: str,
        target_engine_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> ProvisionResult:
        if self.registry is None:
            return ProvisionResult(
                success=False,
                model_id=model_id,
                message="No llm_engines registry is configured.",
            )

        provision_model = getattr(self.registry, "provision_model", None)
        if not callable(provision_model):
            return ProvisionResult(
                success=False,
                model_id=model_id,
                message="Registry does not expose provision_model().",
            )

        req = ProvisionRequest(
            source=source,
            model_id=model_id,
            target_engine_id=target_engine_id,
            options=dict(options or {}),
        )

        try:
            result = provision_model(req)
        except Exception as exc:
            return ProvisionResult(
                success=False,
                model_id=model_id,
                message=f"{type(exc).__name__}: {exc}",
            )

        if isinstance(result, ProvisionResult):
            return result

        if isinstance(result, dict):
            return ProvisionResult(
                success=bool(result.get("success", False)),
                model_id=result.get("model_id", model_id),
                local_ref=result.get("local_ref"),
                message=result.get("message", ""),
            )

        return ProvisionResult(
            success=True,
            model_id=model_id,
            local_ref=getattr(result, "local_ref", None),
            message=getattr(result, "message", "") or "Provision completed.",
        )

    def create_engine(self, engine_id: str, config: Optional[dict[str, Any]] = None) -> Any:
        if engine_id == "echo":
            return EchoEngine()

        if self.registry is not None:
            create_engine = getattr(self.registry, "create_engine", None)
            if callable(create_engine):
                return create_engine(engine_id, config or {})

        raise RuntimeError(
            f"Engine '{engine_id}' is not available. "
            "Wire a llm_engines registry into EngineService to enable real engines."
        )

    def get_engine_health(
        self, engine_id: str, config: Optional[dict[str, Any]] = None
    ) -> EngineHealth:
        if engine_id == "echo":
            return EngineHealth(
                engine_id="echo",
                label="Echo (debug)",
                exists=True,
                reachable=True,
                models_available=True,
                model_count=1,
                status="ok",
                message="Built-in debug engine is ready.",
                details={},
            )

        descriptor = next((e for e in self.list_engines() if e.engine_id == engine_id), None)
        if descriptor is None:
            return EngineHealth(
                engine_id=engine_id,
                label=engine_id,
                exists=False,
                reachable=False,
                models_available=False,
                model_count=0,
                status="error",
                message="Engine is not registered.",
                details={},
            )

        reachable, reach_message, reach_details = self._probe_engine_reachability(
            engine_id, config or {}
        )
        models, models_error = self._list_models_with_error(engine_id, config=config or {})
        model_count = len(models) if models is not None else None
        models_available = (model_count > 0) if model_count is not None else None

        if reachable is None and models_error is None:
            reachable = True

        if reachable is False:
            status = "error"
        elif models_available is False:
            status = "warning"
        elif reachable is True and models_available is True:
            status = "ok"
        else:
            status = "warning"

        message_parts: list[str] = []
        if reach_message:
            message_parts.append(reach_message)
        if models_error:
            message_parts.append(f"Model listing failed: {models_error}")
        elif models_available is False:
            message_parts.append("No models available for this engine.")
        elif models_available is True:
            message_parts.append(f"{model_count} model(s) available.")

        return EngineHealth(
            engine_id=engine_id,
            label=descriptor.label,
            exists=True,
            reachable=reachable,
            models_available=models_available,
            model_count=model_count,
            status=status,
            message=" ".join(message_parts).strip(),
            details=reach_details,
        )

    def list_engine_health(
        self, configs: Optional[dict[str, dict[str, Any]]] = None
    ) -> list[EngineHealth]:
        configs = configs or {}
        return [
            self.get_engine_health(engine.engine_id, config=configs.get(engine.engine_id, {}))
            for engine in self.list_engines()
        ]

    def recommend_default_engine(self, configs: Optional[dict[str, dict[str, Any]]] = None) -> str:
        health_rows = self.list_engine_health(configs=configs)

        for row in health_rows:
            if row.engine_id != "echo" and row.status == "ok" and row.models_available:
                return row.engine_id

        for row in health_rows:
            if row.engine_id != "echo" and row.reachable is True:
                return row.engine_id

        return "echo"

    def engine_health_summary(
        self, configs: Optional[dict[str, dict[str, Any]]] = None
    ) -> list[dict[str, Any]]:
        return [
            {
                "engine_id": row.engine_id,
                "label": row.label,
                "exists": row.exists,
                "reachable": row.reachable,
                "models_available": row.models_available,
                "model_count": row.model_count,
                "status": row.status,
                "message": row.message,
            }
            for row in self.list_engine_health(configs=configs)
        ]

    def _list_models_with_error(
        self,
        engine_id: str,
        *,
        config: Optional[dict[str, Any]] = None,
    ) -> tuple[list[ModelDescriptor], Optional[str]]:
        if engine_id == "echo":
            return [
                ModelDescriptor(model_id="echo", label="echo", source="builtin", installed=True)
            ], None

        if self.registry is None:
            return [], "No llm_engines registry is configured."

        list_models = getattr(self.registry, "list_models", None)
        if not callable(list_models):
            return [], "Registry does not expose list_models()."

        try:
            try:
                models = list_models(engine_id, config or {})
            except TypeError:
                models = list_models(engine_id)
        except Exception as exc:
            return [], f"{type(exc).__name__}: {exc}"

        return [self._coerce_model_descriptor(m, default_source=engine_id) for m in models], None

    def _probe_engine_reachability(
        self,
        engine_id: str,
        config: dict[str, Any],
    ) -> tuple[Optional[bool], str, dict[str, Any]]:
        if self.registry is None:
            return None, "No llm_engines registry is configured.", {}

        for method_name in ("health_check", "ping_engine", "get_engine_status"):
            method = getattr(self.registry, method_name, None)
            if not callable(method):
                continue

            try:
                result = method(engine_id, config)
            except TypeError:
                try:
                    result = method(engine_id)
                except Exception as exc:
                    return False, f"{method_name} failed: {type(exc).__name__}: {exc}", {}
            except Exception as exc:
                return False, f"{method_name} failed: {type(exc).__name__}: {exc}", {}

            reachable, message, details = self._coerce_health_result(result)
            if message:
                return reachable, message, details
            return reachable, "", details

        return None, "No registry health probe available.", {}

    def _coerce_health_result(self, value: Any) -> tuple[Optional[bool], str, dict[str, Any]]:
        if isinstance(value, bool):
            return value, "Engine reachable." if value else "Engine not reachable.", {}

        if isinstance(value, dict):
            reachable = value.get("reachable")
            if reachable is None and "ok" in value:
                reachable = bool(value.get("ok"))
            message = str(value.get("message", "") or "")
            details = {k: v for k, v in value.items() if k not in {"reachable", "ok", "message"}}
            return reachable, message, details

        if hasattr(value, "__dict__") or hasattr(value, "__dataclass_fields__"):
            payload = (
                asdict(value) if hasattr(value, "__dataclass_fields__") else dict(value.__dict__)
            )
            reachable = payload.get("reachable")
            if reachable is None and "ok" in payload:
                reachable = bool(payload.get("ok"))
            message = str(payload.get("message", "") or "")
            details = {k: v for k, v in payload.items() if k not in {"reachable", "ok", "message"}}
            return reachable, message, details

        return None, "", {}

    def _coerce_config_schema(self, value: Any) -> list[EngineConfigField]:
        if not value:
            return []

        fields: list[EngineConfigField] = []
        for item in value:
            if isinstance(item, EngineConfigField):
                fields.append(item)
                continue

            if isinstance(item, dict):
                fields.append(
                    EngineConfigField(
                        name=item.get("name", ""),
                        label=item.get("label", item.get("name", "")),
                        field_type=item.get("field_type", item.get("type", "text")),
                        default=item.get("default"),
                        required=bool(item.get("required", False)),
                        help=item.get("help", ""),
                        placeholder=item.get("placeholder", ""),
                    )
                )
                continue

            payload = (
                asdict(item)
                if hasattr(item, "__dataclass_fields__")
                else getattr(item, "__dict__", {})
            )
            if payload:
                fields.append(
                    EngineConfigField(
                        name=payload.get("name", ""),
                        label=payload.get("label", payload.get("name", "")),
                        field_type=payload.get("field_type", payload.get("type", "text")),
                        default=payload.get("default"),
                        required=bool(payload.get("required", False)),
                        help=payload.get("help", ""),
                        placeholder=payload.get("placeholder", ""),
                    )
                )

        return [field for field in fields if field.name]

    def _heuristic_config_schema(self, engine_id: str) -> list[EngineConfigField]:
        key = engine_id.lower()

        if "ollama" in key:
            return [
                EngineConfigField(
                    name="base_url",
                    label="Base URL",
                    field_type="text",
                    default="http://localhost:11434",
                    help="URL for the Ollama server.",
                ),
                EngineConfigField(
                    name="timeout_s",
                    label="Timeout (seconds)",
                    field_type="int",
                    default=30,
                ),
            ]

        if "vllm" in key:
            return [
                EngineConfigField(
                    name="base_url",
                    label="Base URL",
                    field_type="text",
                    default="http://localhost:8000/v1",
                    help="OpenAI-compatible vLLM endpoint.",
                ),
                EngineConfigField(
                    name="timeout_s",
                    label="Timeout (seconds)",
                    field_type="int",
                    default=30,
                ),
            ]

        if "openai_compat" in key or "openai-compatible" in key:
            return [
                EngineConfigField(
                    name="base_url",
                    label="Base URL",
                    field_type="text",
                    default="",
                    help="OpenAI-compatible endpoint root.",
                ),
                EngineConfigField(
                    name="api_key",
                    label="API key",
                    field_type="password",
                    default="",
                ),
                EngineConfigField(
                    name="timeout_s",
                    label="Timeout (seconds)",
                    field_type="int",
                    default=30,
                ),
            ]

        return []

    def _coerce_engine_descriptor(self, value: Any) -> EngineDescriptor:
        if isinstance(value, EngineDescriptor):
            return value

        if isinstance(value, dict):
            return EngineDescriptor(
                engine_id=value.get("engine_id", value.get("id", "unknown")),
                label=value.get("label", value.get("name", value.get("engine_id", "unknown"))),
                local=bool(value.get("local", True)),
                metadata={
                    k: v
                    for k, v in value.items()
                    if k not in {"engine_id", "id", "label", "name", "local"}
                },
            )

        payload = (
            asdict(value)
            if hasattr(value, "__dataclass_fields__")
            else getattr(value, "__dict__", {})
        )
        engine_id = payload.get("engine_id", payload.get("id", str(value)))
        label = payload.get("label", payload.get("name", engine_id))
        local = bool(payload.get("local", True))
        metadata = {
            k: v
            for k, v in payload.items()
            if k not in {"engine_id", "id", "label", "name", "local"}
        }
        return EngineDescriptor(engine_id=engine_id, label=label, local=local, metadata=metadata)

    def _coerce_model_descriptor(self, value: Any, *, default_source: str) -> ModelDescriptor:
        if isinstance(value, ModelDescriptor):
            return value

        if isinstance(value, dict):
            return ModelDescriptor(
                model_id=value.get("model_id", value.get("id", "unknown")),
                label=value.get("label", value.get("name", value.get("model_id", "unknown"))),
                source=value.get("source", default_source),
                installed=bool(value.get("installed", False)),
                metadata={
                    k: v
                    for k, v in value.items()
                    if k not in {"model_id", "id", "label", "name", "source", "installed"}
                },
            )

        payload = (
            asdict(value)
            if hasattr(value, "__dataclass_fields__")
            else getattr(value, "__dict__", {})
        )
        model_id = payload.get("model_id", payload.get("id", str(value)))
        label = payload.get("label", payload.get("name", model_id))
        source = payload.get("source", default_source)
        installed = bool(payload.get("installed", False))
        metadata = {
            k: v
            for k, v in payload.items()
            if k not in {"model_id", "id", "label", "name", "source", "installed"}
        }
        return ModelDescriptor(
            model_id=model_id,
            label=label,
            source=source,
            installed=installed,
            metadata=metadata,
        )
