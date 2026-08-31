"""
contracts/registry.py

Registry-layer contracts: engine discovery, model listing, provisioning.
These types are distinct from the inference-layer contracts in engine.py.
They are used by the UI registry/service layer, not by backends directly.

ADR: ADR-001 (Engine Capability Model)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class EngineDescriptor:
    """Static description of a registered engine backend."""

    engine_id: str
    label: str
    local: bool = True
    supports_chat: bool = True
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineParameter:
    """Schema descriptor for a single engine configuration parameter."""

    name: str
    label: str
    kind: str  # "str" | "int" | "float" | "bool" | "select" | "path" | "secret"
    required: bool = False
    default: Any = None
    help_text: str = ""
    choices: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EngineConfigSchema:
    """Full configuration schema for an engine."""

    engine_id: str
    parameters: list[EngineParameter] = field(default_factory=list)


@dataclass(frozen=True)
class ModelDescriptor:
    """Description of a model available on a backend."""

    model_id: str
    label: str
    source: str  # "huggingface" | "ollama" | "local" | "endpoint" | "builtin"
    installed: bool = False
    local_path: Optional[str] = None
    size_bytes: Optional[int] = None
    context_length: Optional[int] = None
    quantization: Optional[str] = None
    architecture: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProvisionRequest:
    """Request to download or register a model on a backend."""

    source: str
    model_id: str
    target_engine_id: Optional[str] = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProvisionResult:
    """Result of a provision operation."""

    success: bool
    model_id: str
    message: str = ""
    local_ref: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineInvocationRequest:
    """Simple string-level invocation request (for registry/handle layer)."""

    prompt: str
    model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    settings: dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None


@dataclass(frozen=True)
class EngineInvocationResult:
    """Simple string-level invocation result (for registry/handle layer)."""

    text: str
    model_id: Optional[str]
    metrics: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


@runtime_checkable
class EngineHandle(Protocol):
    """Protocol for a configured, invocable engine instance."""

    engine_id: str

    def invoke(self, request: EngineInvocationRequest) -> EngineInvocationResult: ...


@runtime_checkable
class EngineRegistry(Protocol):
    """Protocol for the engine registry/discovery service."""

    def list_engines(self) -> list[EngineDescriptor]: ...

    def get_engine_schema(self, engine_id: str) -> EngineConfigSchema: ...

    def list_models(self, engine_id: str) -> list[ModelDescriptor]: ...

    def search_models(
        self,
        query: str,
        *,
        source: Optional[str] = None,
        limit: int = 25,
    ) -> list[ModelDescriptor]: ...

    def provision_model(self, request: ProvisionRequest) -> ProvisionResult: ...

    def create_engine(self, engine_id: str, config: dict[str, Any]) -> EngineHandle: ...


__all__ = [
    "EngineDescriptor",
    "EngineParameter",
    "EngineConfigSchema",
    "ModelDescriptor",
    "ProvisionRequest",
    "ProvisionResult",
    "EngineInvocationRequest",
    "EngineInvocationResult",
    "EngineHandle",
    "EngineRegistry",
]
