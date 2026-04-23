from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CapabilityKind(str, Enum):
    ENGINE = "engine"
    MEMORY = "memory"
    RETRIEVER = "retriever"
    INSPECTOR = "inspector"
    AGENT_RUNTIME = "agent_runtime"
    TOOL_PROVIDER = "tool_provider"
    EMBEDDING_PROVIDER = "embedding_provider"
    RAG_PIPELINE = "rag_pipeline"
    UI = "ui"
    OTHER = "other"


@dataclass(frozen=True)
class CapabilityDescriptor:
    kind: CapabilityKind | str
    provider: str
    component: str
    version: str | None = None
    summary: str = ""
    features: tuple[str, ...] = ()
    input_types: tuple[str, ...] = ()
    output_types: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def supports(self, feature: str) -> bool:
        return feature in set(self.features)
