from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from llm_harness_core import OperationResult, TraceEvent as InteropTraceEvent

from .types import EvidenceFlow, EvidenceItem, Section, Turn


@dataclass(frozen=True)
class TokenAccounting:
    """Token budgeting + outcomes for prompt assembly."""

    target_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    # Optional breakdowns (works for Engram memory tiers and for RAG).
    per_origin_budget: dict[str, int] = field(default_factory=dict)
    per_origin_used: dict[str, int] = field(default_factory=dict)

    truncated: bool = False
    compressed: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunMetrics:
    """Runtime metrics for the model call (if performed)."""

    engine: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    inference_optimizations: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


@dataclass(frozen=True)
class ContextResult:
    """The assembled context/prompt plus evidence and accounting."""

    sections: list[Section]
    evidence: list[EvidenceItem] = field(default_factory=list)
    evidence_flows: list[EvidenceFlow] = field(default_factory=list)
    token_accounting: TokenAccounting = field(default_factory=TokenAccounting)
    signals: dict[str, Any] = field(default_factory=dict)  # e.g. surprise, confidence
    notes: list[str] = field(default_factory=list)

    def to_operation_result(self) -> OperationResult[dict[str, Any]]:
        value = {
            "sections": [
                {
                    "title": section.title,
                    "text": section.text,
                    "origin": section.origin,
                    "tokens": section.tokens,
                    "meta": dict(section.meta),
                }
                for section in self.sections
            ],
            "evidence": [item.to_memory_record() for item in self.evidence],
        }
        diagnostics = {
            "signals": dict(self.signals),
            "notes": list(self.notes),
            "evidence_flows": [
                {
                    "source": flow.source,
                    "before_text": flow.before_text,
                    "after_text": flow.after_text,
                    "stage": flow.stage,
                    "score": flow.score,
                    "provenance": dict(flow.provenance),
                    "transformations": list(flow.transformations),
                    "excluded": flow.excluded,
                    "exclusion_reason": flow.exclusion_reason,
                    "meta": dict(flow.meta),
                }
                for flow in self.evidence_flows
            ],
            "token_accounting": {
                "target_tokens": self.token_accounting.target_tokens,
                "total_tokens": self.token_accounting.total_tokens,
                "per_origin_budget": dict(self.token_accounting.per_origin_budget),
                "per_origin_used": dict(self.token_accounting.per_origin_used),
                "truncated": self.token_accounting.truncated,
                "compressed": self.token_accounting.compressed,
                "notes": list(self.token_accounting.notes),
            },
        }
        return OperationResult.success(value, diagnostics=diagnostics)


@dataclass(frozen=True)
class TraceEvent(InteropTraceEvent):
    """Shared interop event with compatibility aliases for older inspector code."""

    @property
    def kind(self) -> str:
        return self.event_type

    @property
    def fields(self) -> dict[str, Any]:
        return self.payload

    @classmethod
    def from_interop(cls, event: InteropTraceEvent) -> "TraceEvent":
        if isinstance(event, cls):
            return event
        return cls(
            event_type=event.event_type,
            source_package=event.source_package,
            source_component=event.source_component,
            payload=dict(event.payload),
            severity=event.severity,
            message=event.message,
            event_id=event.event_id,
            span_id=event.span_id,
            parent_span_id=event.parent_span_id,
            ts=event.ts,
            tags=tuple(event.tags),
        )


@dataclass(frozen=True)
class Trace:
    """One end-to-end trace for a turn/run."""

    turn: Turn
    context: ContextResult
    metrics: RunMetrics = field(default_factory=RunMetrics)
    events: list[TraceEvent] = field(default_factory=list)

    def to_interop_result(self) -> OperationResult[dict[str, Any]]:
        diagnostics = {
            "turn": {
                "role": self.turn.role,
                "session_id": self.turn.session_id,
                "ts": self.turn.ts,
            },
            "metrics": {
                "engine": self.metrics.engine,
                "model": self.metrics.model,
                "latency_ms": self.metrics.latency_ms,
                "prompt_tokens": self.metrics.prompt_tokens,
                "output_tokens": self.metrics.output_tokens,
                "inference_optimizations": list(self.metrics.inference_optimizations),
                "error": self.metrics.error,
            },
            "event_count": len(self.events),
        }
        context_result = self.context.to_operation_result()
        merged = dict(context_result.diagnostics)
        merged.update(diagnostics)
        return OperationResult.success(context_result.value or {}, diagnostics=merged)

    def to_interop_events(self) -> list[InteropTraceEvent]:
        return [TraceEvent.from_interop(event) for event in self.events]
