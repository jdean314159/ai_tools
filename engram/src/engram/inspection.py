"""
engram.inspection — prompt-build trace types..

These dataclasses record what happened during prompt assembly: which memory
sections were included, what evidence was retrieved, how token budget was
spent, and what the final prompt looked like.

These are prompt-building-specific types. The broader observability
vocabulary (Trace, Turn, RunMetrics, etc.) lives in llm_inspector.core.
The engram adapter in llm_inspector converts these types to inspector
types field-by-field — see llm_inspector.adapters.engram_adapter.

Aliases at the bottom of this module map the inspector names
(EvidenceItem, Section) onto the local names so code importing either
name from this module works correctly.
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

    source: str  # e.g. "working", "episodic", "semantic", "cold"
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


def _evidence_provenance(evidence: Any) -> dict[str, Any]:
    meta = dict(getattr(evidence, "meta", {}) or {})
    prov: dict[str, Any] = {
        "source": getattr(evidence, "source", "memory"),
        "augmenter": "engram",
    }
    for key in (
        "session_id",
        "project_id",
        "episode_id",
        "topic_key",
        "tenant",
        "source",
        "writer",
        "trust",
        "quarantined",
    ):
        if key in meta:
            prov[key] = meta[key]
    return prov


def _evidence_transformations(evidence: Any) -> tuple[str, ...]:
    transformations = ["selected"]
    text = str(getattr(evidence, "text", "") or "")
    meta = dict(getattr(evidence, "meta", {}) or {})
    if getattr(evidence, "source", "") == "working" and ": " in text[:24]:
        transformations.append("role_prefixed")
    if meta.get("truncated") or meta.get("compressed"):
        transformations.append("truncated")
    return tuple(transformations)


def build_interop_events(trace: Any) -> list:
    from llm_harness_core import TraceEvent

    events = [
        TraceEvent(
            event_type="prompt_build_completed",
            source_package="engram",
            source_component="PromptBuildTrace",
            payload={
                "section_count": len(trace.sections),
                "evidence_count": len(trace.evidence),
                "compressed": trace.token_accounting.compressed,
                "truncated": trace.token_accounting.truncated,
                "total_tokens": trace.token_accounting.total_tokens,
            },
            message="Prompt build finished.",
            tags=("prompt", "memory"),
        )
    ]
    for evidence in trace.evidence:
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
                    "provenance": _evidence_provenance(evidence),
                    "transformations": list(_evidence_transformations(evidence)),
                },
                message=f"Included {evidence.source} memory evidence.",
                tags=("memory", evidence.source),
            )
        )
    return events


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
        return build_interop_events(self)


# ---------------------------------------------------------------------------
# Aliases — map llm_inspector observability names onto local names.
# These are in-module aliases only; no cross-package import is introduced.
# ---------------------------------------------------------------------------
EvidenceItem = EvidenceTrace  # llm_inspector calls this EvidenceItem
Section = PromptSectionTrace  # llm_inspector calls this Section


__all__ = [
    "PromptSectionTrace",
    "EvidenceTrace",
    "TokenAccountingTrace",
    "PromptBuildTrace",
    # aliases
    "EvidenceItem",
    "Section",
]
