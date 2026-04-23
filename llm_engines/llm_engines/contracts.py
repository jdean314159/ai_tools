"""Backward-compatible re-export for registry contracts.

Historically this module duplicated a subset of registry/discovery contract
classes. The canonical source is now :mod:`llm_engines.contracts`.
Keep this file as a thin shim so older imports continue to resolve without
creating a second contract authority.
"""

from __future__ import annotations

from .contracts import (
    EngineConfigSchema,
    EngineDescriptor,
    EngineHandle,
    EngineInvocationRequest,
    EngineInvocationResult,
    EngineParameter,
    EngineRegistry,
    ModelDescriptor,
    ProvisionRequest,
    ProvisionResult,
)

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
