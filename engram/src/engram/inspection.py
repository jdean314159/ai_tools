"""
engram.inspection — prompt-build trace types.

These dataclasses record what happened during prompt assembly: which memory
sections were included, what evidence was retrieved, how token budget was
spent, and what the final prompt looked like.

These are prompt-building-specific types.  The broader observability
vocabulary (Trace, Turn, RunMetrics, etc.) lives in llm_inspector.core.
The engram adapter in llm_inspector converts these types to inspector
types field-by-field — see llm_inspector.adapters.engram_adapter.

Aliases at the bottom of this module map the inspector names
(EvidenceItem, Section) onto the local names so code importing either
name from this module works correctly.

This is the canonical home of these types.  engram_lite.inspection
re-exports from here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from llm_harness_core import MemoryRecord, TraceEvent


@dataclass(frozen=True)
class PromptSectionTrace:
    """One section of the assembled prompt (system, working, episodic, user, etc.)."""
    title: str
    origin: str
    text: str
    tokens: Optional[int] = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceTrace:
    """One piece of retrieved context that contributed to the prompt."""
    source: str   # e.g. "working", "episodic", "semantic", "cold"
    text: str
    score: Optional[float] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_memory_record(self) -> MemoryRecord:
        return MemoryRecord(
            text=self.text,
            source=self.source,
            score=self.score,
            metadata=dict(self.meta),
        )


@dataclass(frozen=True)
class TokenAccountingTrace:
    """Token budget accounting for a single prompt build."""
    target_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    per_origin_budget: dict[str, int] = field(default_factory=dict)
    per_origin_used: dict[str, int] = field(default_factory=dict)
    truncated: bool = False
    compressed: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PromptBuildTrace:
    """Complete trace for one prompt-build cycle."""
    sections: list[PromptSectionTrace] = field(default_factory=list)
    evidence: list[EvidenceTrace] = field(default_factory=list)
    token_accounting: TokenAccountingTrace = field(default_factory=TokenAccountingTrace)
    flags: dict[str, Any] = field(default_factory=dict)
    final_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_interop_events(self) -> list[TraceEvent]:
        events: list[TraceEvent] = [
            TraceEvent(
                event_type="prompt_build_completed",
                source_package="engram",
                source_component="PromptBuildTrace",
                payload={
                    "section_count": len(self.sections),
                    "evidence_count": len(self.evidence),
                    "compressed": self.token_accounting.compressed,
                    "truncated": self.token_accounting.truncated,
                    "total_tokens": self.token_accounting.total_tokens,
                },
                message="Prompt build finished.",
                tags=("prompt", "memory"),
            )
        ]
        for evidence in self.evidence:
            events.append(
                TraceEvent(
                    event_type="memory_evidence_included",
                    source_package="engram",
                    source_component="PromptBuildTrace",
                    payload={
                        "source": evidence.source,
                        "text": evidence.text,
                        "score": evidence.score,
                        "metadata": dict(evidence.meta),
                    },
                    message=f"Included {evidence.source} memory evidence.",
                    tags=("memory", evidence.source),
                )
            )
        return events


# ---------------------------------------------------------------------------
# Aliases — map llm_inspector observability names onto local names.
# ---------------------------------------------------------------------------
EvidenceItem = EvidenceTrace
Section = PromptSectionTrace


__all__ = [
    "PromptSectionTrace",
    "EvidenceTrace",
    "TokenAccountingTrace",
    "PromptBuildTrace",
    "EvidenceItem",
    "Section",
]
