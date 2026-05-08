from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from llm_inspector.core import ContextResult as InspectContextResult, EvidenceItem, RunMetrics, Section, TokenAccounting, Trace, TraceEvent
from llm_inspector.protocols import AugmentRequest, ContextAugmenter


def _copy_meta(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_engram_lite_event(event: Any) -> TraceEvent:
    """Normalize delegated Engram events to the Engram Lite adapter boundary.

    Engram Lite is now a facade over Engram, so raw prompt traces may contain
    events whose source_package is "engram".  The llm_inspector adapter should
    expose the user-facing adapter source as "engram_lite" while preserving
    the upstream source in the payload.
    """
    converted = TraceEvent.from_interop(event)
    if converted.source_package == "engram_lite":
        return converted

    payload = dict(converted.payload)
    payload.setdefault("upstream_source_package", converted.source_package)
    payload.setdefault("upstream_source_component", converted.source_component)

    return TraceEvent(
        event_type=converted.event_type,
        source_package="engram_lite",
        source_component=converted.source_component or "EngramLiteAugmenter",
        payload=payload,
        severity=converted.severity,
        message=converted.message,
        event_id=converted.event_id,
        span_id=converted.span_id,
        parent_span_id=converted.parent_span_id,
        ts=converted.ts,
        tags=converted.tags,
    )


@dataclass
class EngramLiteAugmenter(ContextAugmenter):
    base_dir: Path
    project_id: str = "default"
    max_prompt_tokens: Optional[int] = None
    reserve_output_tokens: int = 512
    _name: str = "engram_lite"

    @property
    def name(self) -> str:
        return self._name

    def augment(self, req: AugmentRequest) -> Trace:
        from engram_lite import ProjectMemory

        pm = ProjectMemory(base_dir=self.base_dir, project_id=self.project_id, session_id=req.session_id)
        pm.new_session(req.session_id)
        pm.add_turn("user", req.turn.text, req.session_id)
        result = pm.build_prompt(
            user_message=req.turn.text,
            query=req.query or req.turn.text,
            max_prompt_tokens=self.max_prompt_tokens,
            reserve_output_tokens=self.reserve_output_tokens,
            return_trace=True,
        )
        prompt_trace = result.get("trace")
        if prompt_trace is None:
            raise RuntimeError("Engram Lite did not return a prompt trace.")

        sections = [
            Section(title=s.title, text=s.text, origin=s.origin, tokens=s.tokens, meta=_copy_meta(getattr(s, "meta", {})))
            for s in getattr(prompt_trace, "sections", []) or []
        ]
        evidence = [
            EvidenceItem(text=e.text, source=e.source, score=e.score, meta=_copy_meta(getattr(e, "meta", {})))
            for e in getattr(prompt_trace, "evidence", []) or []
        ]
        token_trace = getattr(prompt_trace, "token_accounting", None)
        token_acc = TokenAccounting(
            target_tokens=getattr(token_trace, "target_tokens", None),
            total_tokens=getattr(token_trace, "total_tokens", None),
            per_origin_budget=dict(getattr(token_trace, "per_origin_budget", {}) or {}),
            per_origin_used=dict(getattr(token_trace, "per_origin_used", {}) or {}),
            truncated=bool(getattr(token_trace, "truncated", False)),
            compressed=bool(getattr(token_trace, "compressed", False)),
            notes=list(getattr(token_trace, "notes", []) or []),
        )
        flags = dict(getattr(prompt_trace, "flags", {}) or {})
        context = InspectContextResult(sections=sections, evidence=evidence, token_accounting=token_acc, signals=flags)
        prompt_tokens = result.get("prompt_tokens")
        if not isinstance(prompt_tokens, int):
            prompt_tokens = token_acc.total_tokens
        metrics = RunMetrics(engine="engram_lite", model=None, prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None)

        raw_events = getattr(prompt_trace, "to_interop_events", lambda: [])()
        events = [_normalize_engram_lite_event(event) for event in raw_events]
        if not events:
            events = [
                TraceEvent(
                    event_type="prompt_build_completed",
                    source_package="engram_lite",
                    source_component="EngramLiteAugmenter",
                    payload={
                        "compressed": bool(flags.get("compressed", False)),
                        "truncated": bool(flags.get("truncated", False)),
                        "query": flags.get("query"),
                    },
                    message="Built prompt via Engram Lite trace API",
                    tags=("prompt", "memory"),
                )
            ]
        return Trace(turn=req.turn, context=context, metrics=metrics, events=events)



def make_engram_lite(**kwargs) -> EngramLiteAugmenter:
    if "base_dir" in kwargs:
        kwargs["base_dir"] = Path(kwargs["base_dir"])
    return EngramLiteAugmenter(**kwargs)
