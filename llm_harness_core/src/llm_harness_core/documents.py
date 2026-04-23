from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievedDocument:
    text: str
    source: str
    doc_id: str | None = None
    score: float | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRecord:
    text: str
    source: str
    record_id: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
