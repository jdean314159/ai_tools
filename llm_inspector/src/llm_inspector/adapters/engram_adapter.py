from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from llm_harness_core import OperationResult
from llm_inspector.core import (
    ContextResult as InspectContextResult,
    EvidenceFlow,
    EvidenceItem,
    RunMetrics,
    Section,
    TokenAccounting,
    Trace,
    TraceEvent,
)
from llm_inspector.protocols import AugmentRequest, ContextAugmenter


def _copy_meta(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _event_provenance(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("provenance")
    return dict(value) if isinstance(value, dict) else {}


def _event_transformations(payload: dict[str, Any]) -> tuple[str, ...]:
    value = payload.get("transformations")
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def _interop_events_to_evidence_flows(events: list[Any]) -> list[EvidenceFlow]:
    flows: list[EvidenceFlow] = []
    for event in events:
        payload = dict(getattr(event, "payload", {}) or {})
        event_type = getattr(event, "event_type", None)
        if event_type == "memory_evidence_included":
            metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
            before_text = (
                metadata.get("raw_text")
                or metadata.get("source_text")
                or metadata.get("original_text")
                or payload.get("text")
                or ""
            )
            after_text = payload.get("text") or before_text
            flows.append(
                EvidenceFlow(
                    source=str(payload.get("source") or "memory"),
                    before_text=str(before_text),
                    after_text=str(after_text),
                    stage="prompt_included",
                    score=payload.get("score"),
                    provenance=_event_provenance(payload),
                    transformations=_event_transformations(payload),
                    meta={"event_type": event_type, **metadata},
                )
            )
        elif event_type == "memory_evidence_excluded":
            metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
            before_text = payload.get("text") or metadata.get("raw_text") or ""
            flows.append(
                EvidenceFlow(
                    source=str(payload.get("source") or "memory"),
                    before_text=str(before_text),
                    after_text="",
                    stage="excluded",
                    score=payload.get("score"),
                    provenance=_event_provenance(payload),
                    transformations=_event_transformations(payload),
                    excluded=True,
                    exclusion_reason=str(payload.get("reason") or payload.get("exclusion_reason") or "excluded"),
                    meta={"event_type": event_type, **metadata},
                )
            )
    return flows


def _trace_to_inspector_trace(
    req: AugmentRequest,
    prompt_trace: Any,
    *,
    prompt_tokens: int | None = None,
    interop_events: list[Any] | None = None,
) -> Trace:
    sections = [
        Section(
            title=s.title,
            text=s.text,
            origin=s.origin,
            tokens=s.tokens,
            meta=_copy_meta(getattr(s, "meta", {})),
        )
        for s in getattr(prompt_trace, "sections", []) or []
    ]

    evidence = [
        EvidenceItem(
            text=e.text,
            source=e.source,
            score=e.score,
            meta=_copy_meta(getattr(e, "meta", {})),
        )
        for e in getattr(prompt_trace, "evidence", []) or []
    ]

    trace_token_acc = getattr(prompt_trace, "token_accounting", None)
    raw_events = list(interop_events or [])
    if not raw_events:
        raw_events = getattr(prompt_trace, "to_interop_events", lambda: [])()
    token_acc = TokenAccounting(
        target_tokens=getattr(trace_token_acc, "target_tokens", None),
        total_tokens=getattr(trace_token_acc, "total_tokens", None),
        per_origin_budget=dict(getattr(trace_token_acc, "per_origin_budget", {}) or {}),
        per_origin_used=dict(getattr(trace_token_acc, "per_origin_used", {}) or {}),
        truncated=bool(getattr(trace_token_acc, "truncated", False)),
        compressed=bool(getattr(trace_token_acc, "compressed", False)),
        notes=list(getattr(trace_token_acc, "notes", []) or []),
    )

    flags = dict(getattr(prompt_trace, "flags", {}) or {})
    evidence_flows = _interop_events_to_evidence_flows(raw_events)
    context = InspectContextResult(
        sections=sections,
        evidence=evidence,
        evidence_flows=evidence_flows,
        token_accounting=token_acc,
        signals=flags,
    )

    if not isinstance(prompt_tokens, int):
        prompt_tokens = token_acc.total_tokens
    metrics = RunMetrics(
        engine="engram",
        model=None,
        latency_ms=None,
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        output_tokens=None,
        error=None,
    )

    events = [TraceEvent.from_interop(event) for event in raw_events]
    if not events:
        events = [
            TraceEvent(
                event_type="prompt_build_completed",
                source_package="engram",
                source_component="EngramAugmenter",
                payload={
                    "compressed": bool(flags.get("compressed", False)),
                    "truncated": bool(flags.get("truncated", False)),
                    "query": flags.get("query"),
                },
                message="Built prompt via Engram trace API",
                tags=("prompt", "memory"),
            )
        ]

    return Trace(
        turn=req.turn,
        context=context,
        metrics=metrics,
        events=events,
    )


@dataclass
class EngramAugmenter(ContextAugmenter):
    """Thin adapter that maps Engram prompt-building output into llm_inspector.Trace."""

    base_dir: Path
    profile: str = "default_local"
    project_id: str = "default"
    project_type: str = "programming_assistant"
    max_prompt_tokens: Optional[int] = None
    reserve_output_tokens: int = 512

    _name: str = "engram"

    @property
    def name(self) -> str:
        return self._name

    def _make_project_memory(self, req: AugmentRequest):
        from engram.project_memory import ProjectMemory

        try:
            from engram import ProjectType  # type: ignore
        except Exception:
            from engram.project_memory import ProjectType  # type: ignore

        pm = ProjectMemory(
            project_id=self.project_id,
            project_type=ProjectType(self.project_type),
            base_dir=Path(self.base_dir),
            session_id=req.session_id,
            llm_engine=None,
        )
        pm.new_session(req.session_id)
        pm.add_turn("user", req.turn.text)
        return pm

    def _augment_via_interop(self, pm: Any, req: AugmentRequest) -> Trace | None:
        build_prompt_interop = getattr(pm, "build_prompt_interop", None)
        if not callable(build_prompt_interop):
            return None

        result = build_prompt_interop(
            user_message=req.turn.text,
            query=req.query or req.turn.text,
            max_prompt_tokens=self.max_prompt_tokens,
            reserve_output_tokens=self.reserve_output_tokens,
        )
        if not isinstance(result, OperationResult) or not result.ok:
            return None
        prompt_trace = result.diagnostics.get("trace")
        if prompt_trace is None:
            return None
        return _trace_to_inspector_trace(
            req,
            prompt_trace,
            prompt_tokens=result.diagnostics.get("prompt_tokens"),
            interop_events=result.diagnostics.get("trace_events"),
        )

    def _augment_via_legacy_trace(self, pm: Any, req: AugmentRequest) -> Trace:
        result = pm.build_prompt(
            user_message=req.turn.text,
            query=req.query or req.turn.text,
            max_prompt_tokens=self.max_prompt_tokens,
            reserve_output_tokens=self.reserve_output_tokens,
            return_trace=True,
        )

        prompt_trace = result.get("trace")
        if prompt_trace is None:
            raise RuntimeError(
                "Engram did not return a prompt trace. "
                "This adapter expects either build_prompt_interop(...) diagnostics['trace'] or "
                "build_prompt(..., return_trace=True) to provide a PromptBuildTrace-compatible object."
            )
        return _trace_to_inspector_trace(req, prompt_trace, prompt_tokens=result.get("prompt_tokens"))

    def augment(self, req: AugmentRequest) -> Trace:
        pm = self._make_project_memory(req)
        try:
            interop_trace = self._augment_via_interop(pm, req)
            if interop_trace is not None:
                return interop_trace
            return self._augment_via_legacy_trace(pm, req)
        finally:
            close = getattr(pm, "close", None)
            if callable(close):
                close()


def make_engram(**kwargs) -> EngramAugmenter:
    try:
        import engram  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "Engram adapter requires Engram installed. Install with: pip install 'llm_inspector[engram]'"
        ) from e

    if "base_dir" in kwargs:
        kwargs["base_dir"] = Path(kwargs["base_dir"])
    return EngramAugmenter(**kwargs)
