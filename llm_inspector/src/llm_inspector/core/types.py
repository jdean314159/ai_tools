"""
llm_inspector.core.types — canonical observability vocabulary.

These types describe the *inspector* view of a prompt run: turns,
assembled sections, evidence items, and the trace as a whole. They are
independent of any specific augmentation system, but can convert to the
shared llm_harness_core interoperability types where appropriate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from llm_harness_core import LLMMessage, MemoryRecord, RetrievedDocument

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Turn:
    """A single conversational turn."""

    role: Role
    text: str
    session_id: str = "default"
    ts: Optional[float] = None  # epoch seconds

    def to_interop_message(self) -> LLMMessage:
        metadata: dict[str, Any] = {"session_id": self.session_id}
        if self.ts is not None:
            metadata["ts"] = self.ts
        return LLMMessage(role=self.role, content=self.text, metadata=metadata)


@dataclass(frozen=True)
class EvidenceItem:
    """Any piece of supporting context (memory hit, retrieved chunk, tool output, etc.)."""

    text: str
    source: str  # e.g. "episodic", "semantic", "rag", "tool", "working"
    score: Optional[float] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_memory_record(self) -> MemoryRecord:
        return MemoryRecord(
            text=self.text,
            source=self.source,
            score=self.score,
            metadata=dict(self.meta),
        )

    def to_retrieved_document(self) -> RetrievedDocument:
        return RetrievedDocument(
            text=self.text,
            source=self.source,
            score=self.score,
            title=self.meta.get("title"),
            doc_id=self.meta.get("doc_id") or self.meta.get("record_id"),
            metadata=dict(self.meta),
        )


@dataclass(frozen=True)
class EvidenceFlow:
    """A before/after view of evidence as it moves toward final prompt contribution."""

    source: str
    before_text: str
    after_text: str
    stage: str = "prompt_included"
    score: Optional[float] = None
    provenance: dict[str, Any] = field(default_factory=dict)
    transformations: tuple[str, ...] = ()
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Section:
    """A section of the assembled prompt."""

    title: str
    text: str
    origin: str  # e.g. "system", "user", "working", "episodic", "semantic", "rag"
    tokens: Optional[int] = None
    meta: dict[str, Any] = field(default_factory=dict)
