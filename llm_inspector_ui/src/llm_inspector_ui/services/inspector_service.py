from __future__ import annotations

import json
from typing import Any, Iterable

from llm_inspector import (
    artifact_inspection_to_dict,
    describe_inspector,
    inspect_artifact,
)
from llm_harness_core import ArtifactValidationError, artifact_from_dict
from llm_inspector.core import (
    ContextResult,
    EvidenceItem,
    RunMetrics,
    Section,
    TokenAccounting,
    Trace,
    TraceEvent,
    Turn,
)
from llm_inspector.core.serialize import to_dict
from llm_inspector.export.bundle_export import bundle_to_dict
from llm_inspector.export.diff_export import diff_to_dict
from llm_inspector.export.json_export import report_to_dict
from llm_inspector.inspectors.bundle import build_bundle
from llm_inspector.inspectors.context_inspector import ComparisonReport, NamedTrace
from llm_inspector.inspectors.diff import diff_traces


class InspectorService:
    """
    Bridge from augmenter output into llm_inspector's normalized Trace model.

    Output is serialized to plain dicts for storage/UI, but compare/diff/bundle
    run through llm_inspector's real dataclasses and inspector helpers.
    """

    def describe_component(self):
        return describe_inspector(self)

    def replay_artifact_json(
        self,
        payload: bytes,
        *,
        max_bytes: int = 5_000_000,
    ) -> dict[str, Any]:
        """Parse and inspect one shared run artifact without executing it."""
        if len(payload) > max_bytes:
            raise ValueError(f"Artifact exceeds the {max_bytes}-byte replay limit.")
        try:
            decoded = json.loads(payload.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("artifact JSON must contain an object")
            artifact = artifact_from_dict(decoded)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ArtifactValidationError,
            ValueError,
        ) as exc:
            raise ValueError(f"Invalid run artifact: {type(exc).__name__}") from None
        return artifact_inspection_to_dict(inspect_artifact(artifact))

    def inspect(
        self,
        *,
        augmenter_id: str,
        augment_result: Any,
        user_text: str,
        session_id: str = "default",
    ) -> dict[str, Any]:
        trace = self._normalize_to_trace(
            augmenter_id=augmenter_id,
            augment_result=augment_result,
            user_text=user_text,
            session_id=session_id,
        )
        return to_dict(trace)

    def compare(self, named_traces: Iterable[tuple[str, Any]], *, query: str) -> dict[str, Any]:
        report = ComparisonReport(
            query=query,
            traces=[
                NamedTrace(name=name, trace=self._trace_from_any(trace))
                for name, trace in named_traces
            ],
        )
        return report_to_dict(report)

    def diff(
        self,
        left_trace: Any,
        right_trace: Any,
        *,
        name_a: str = "A",
        name_b: str = "B",
    ) -> dict[str, Any]:
        left = self._trace_from_any(left_trace)
        right = self._trace_from_any(right_trace)
        return diff_to_dict(diff_traces(left, right, name_a=name_a, name_b=name_b))

    def bundle(self, named_traces: Iterable[tuple[str, Any]], *, query: str) -> dict[str, Any]:
        report = ComparisonReport(
            query=query,
            traces=[
                NamedTrace(name=name, trace=self._trace_from_any(trace))
                for name, trace in named_traces
            ],
        )
        return bundle_to_dict(build_bundle(report))

    def _normalize_to_trace(
        self,
        *,
        augmenter_id: str,
        augment_result: Any,
        user_text: str,
        session_id: str,
    ) -> Trace:
        source = self._trace_payload(getattr(augment_result, "trace", None))
        if "turn" in source and "context" in source:
            return self._trace_from_serialized_dict(source)

        sections = self._sections_from_source(source, getattr(augment_result, "prompt", ""))
        evidence = self._evidence_from_source(source)
        token_accounting = self._token_accounting_from_source(
            source,
            prompt_tokens=getattr(augment_result, "prompt_tokens", None),
            compressed=bool(getattr(augment_result, "compressed", False)),
        )
        signals = dict(source.get("flags", {}) or {})
        signals.setdefault("augmenter_id", augmenter_id)

        context = ContextResult(
            sections=sections,
            evidence=evidence,
            token_accounting=token_accounting,
            signals=signals,
            notes=[],
        )

        metrics = RunMetrics(
            engine=None,
            model=None,
            latency_ms=None,
            prompt_tokens=getattr(augment_result, "prompt_tokens", None),
            output_tokens=None,
            error=None,
        )

        events = [
            TraceEvent(
                event_type="augmenter_trace_normalized",
                source_package="llm_inspector_ui",
                source_component="InspectorService",
                payload={"augmenter_id": augmenter_id},
                severity="info",
                message="Normalized augmenter output into llm_inspector Trace",
            )
        ]

        return Trace(
            turn=Turn(role="user", text=user_text, session_id=session_id),
            context=context,
            metrics=metrics,
            events=events,
        )

    def _trace_from_any(self, value: Any) -> Trace:
        if isinstance(value, Trace):
            return value

        payload = self._trace_payload(value)
        if "turn" in payload and "context" in payload:
            return self._trace_from_serialized_dict(payload)

        sections = self._sections_from_source(payload, payload.get("final_prompt", ""))
        evidence = self._evidence_from_source(payload)
        token_accounting = self._token_accounting_from_source(
            payload,
            prompt_tokens=payload.get("prompt_tokens"),
            compressed=bool(payload.get("compressed", False)),
        )
        context = ContextResult(
            sections=sections,
            evidence=evidence,
            token_accounting=token_accounting,
            signals=dict(payload.get("flags", {}) or {}),
            notes=[],
        )
        return Trace(
            turn=Turn(role="user", text="", session_id="default"),
            context=context,
            metrics=RunMetrics(),
            events=[],
        )

    def _trace_from_serialized_dict(self, data: dict[str, Any]) -> Trace:
        turn_data = data.get("turn", {}) or {}
        context_data = data.get("context", {}) or {}
        metrics_data = data.get("metrics", {}) or {}
        events_data = data.get("events", []) or []

        turn = Turn(
            role=turn_data.get("role", "user"),
            text=turn_data.get("text", ""),
            session_id=turn_data.get("session_id", "default"),
            ts=turn_data.get("ts"),
        )

        sections = [
            Section(
                title=item.get("title", ""),
                text=item.get("text", ""),
                origin=item.get("origin", ""),
                tokens=item.get("tokens"),
                meta=dict(item.get("meta", {}) or {}),
            )
            for item in (context_data.get("sections", []) or [])
        ]

        evidence = [
            EvidenceItem(
                text=item.get("text", ""),
                source=item.get("source", ""),
                score=item.get("score"),
                meta=dict(item.get("meta", item.get("metadata", {})) or {}),
            )
            for item in (context_data.get("evidence", []) or [])
        ]

        ta = context_data.get("token_accounting", {}) or {}
        token_accounting = TokenAccounting(
            target_tokens=ta.get("target_tokens"),
            total_tokens=ta.get("total_tokens"),
            per_origin_budget=dict(ta.get("per_origin_budget", {}) or {}),
            per_origin_used=dict(ta.get("per_origin_used", {}) or {}),
            truncated=bool(ta.get("truncated", False)),
            compressed=bool(ta.get("compressed", False)),
            notes=list(ta.get("notes", []) or []),
        )

        context = ContextResult(
            sections=sections,
            evidence=evidence,
            token_accounting=token_accounting,
            signals=dict(context_data.get("signals", {}) or {}),
            notes=list(context_data.get("notes", []) or []),
        )

        metrics = RunMetrics(
            engine=metrics_data.get("engine"),
            model=metrics_data.get("model"),
            latency_ms=metrics_data.get("latency_ms"),
            prompt_tokens=metrics_data.get("prompt_tokens"),
            output_tokens=metrics_data.get("output_tokens"),
            error=metrics_data.get("error"),
        )

        events = [
            TraceEvent(
                event_type=item.get("event_type") or item.get("kind", ""),
                source_package=item.get("source_package", ""),
                source_component=item.get("source_component", ""),
                payload=dict(item.get("payload", item.get("fields", {})) or {}),
                severity=item.get("severity", "info"),
                message=item.get("message"),
                event_id=item.get("event_id")
                or TraceEvent(
                    event_type="placeholder",
                    source_package="llm_inspector_ui",
                    source_component="InspectorService",
                ).event_id,
                span_id=item.get("span_id"),
                parent_span_id=item.get("parent_span_id"),
                ts=item.get("ts"),
                tags=tuple(item.get("tags", ()) or ()),
            )
            for item in events_data
        ]

        return Trace(turn=turn, context=context, metrics=metrics, events=events)

    def _trace_payload(self, trace: Any) -> dict[str, Any]:
        if trace is None:
            return {}
        if isinstance(trace, dict):
            return trace
        if hasattr(trace, "to_dict") and callable(trace.to_dict):
            value = trace.to_dict()
            return value if isinstance(value, dict) else {}
        return to_dict(trace) if hasattr(trace, "__dataclass_fields__") else {}

    def _sections_from_source(self, source: dict[str, Any], prompt: str) -> list[Section]:
        sections_data = list(source.get("sections", []) or [])
        sections = [
            Section(
                title=item.get("title", ""),
                text=item.get("text", ""),
                origin=item.get("origin", ""),
                tokens=item.get("tokens"),
                meta=dict(item.get("meta", {}) or {}),
            )
            for item in sections_data
        ]

        has_prompt_section = any(s.origin == "prompt" for s in sections)
        final_prompt = source.get("final_prompt")
        if not has_prompt_section and isinstance(final_prompt, str) and final_prompt:
            sections.append(
                Section(
                    title="Final prompt",
                    text=final_prompt,
                    origin="prompt",
                    tokens=None,
                    meta={},
                )
            )
        elif not has_prompt_section and isinstance(prompt, str) and prompt:
            sections.append(
                Section(
                    title="Final prompt",
                    text=prompt,
                    origin="prompt",
                    tokens=None,
                    meta={},
                )
            )

        return sections

    def _evidence_from_source(self, source: dict[str, Any]) -> list[EvidenceItem]:
        return [
            EvidenceItem(
                text=item.get("text", ""),
                source=item.get("source", ""),
                score=item.get("score"),
                meta=dict(item.get("meta", item.get("metadata", {})) or {}),
            )
            for item in (source.get("evidence", []) or [])
        ]

    def _token_accounting_from_source(
        self,
        source: dict[str, Any],
        *,
        prompt_tokens: Any,
        compressed: bool,
    ) -> TokenAccounting:
        ta = source.get("token_accounting", {}) or {}
        return TokenAccounting(
            target_tokens=ta.get("target_tokens"),
            total_tokens=ta.get("total_tokens", prompt_tokens),
            per_origin_budget=dict(ta.get("per_origin_budget", {}) or {}),
            per_origin_used=dict(ta.get("per_origin_used", {}) or {}),
            truncated=bool(ta.get("truncated", False)),
            compressed=bool(ta.get("compressed", compressed)),
            notes=list(ta.get("notes", []) or []),
        )
