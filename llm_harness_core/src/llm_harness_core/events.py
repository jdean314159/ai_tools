from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

Severity = Literal["debug", "info", "warning", "error"]


@dataclass(frozen=True)
class TraceEvent:
    event_type: str
    source_package: str
    source_component: str
    payload: dict[str, Any] = field(default_factory=dict)
    severity: Severity = "info"
    message: str | None = None
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    span_id: str | None = None
    parent_span_id: str | None = None
    ts: float | None = None
    tags: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        """Compatibility name used by early Inspector consumers."""
        return self.event_type

    @property
    def fields(self) -> dict[str, Any]:
        """Compatibility name used by early Inspector consumers."""
        return self.payload
