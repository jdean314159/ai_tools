from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_event(item: Any) -> dict[str, Any]:
    payload = _as_dict(item)
    if not payload:
        return {}

    event_type = payload.get("event_type") or payload.get("kind") or ""
    fields = payload.get("payload")
    if not isinstance(fields, dict):
        fields = payload.get("fields")
    if not isinstance(fields, dict):
        fields = {}

    tags = payload.get("tags", ())
    if isinstance(tags, list):
        tags = tuple(tags)
    elif not isinstance(tags, tuple):
        tags = ()

    return {
        "kind": event_type,
        "event_type": event_type,
        "message": payload.get("message", ""),
        "fields": fields,
        "payload": fields,
        "source_package": payload.get("source_package", ""),
        "source_component": payload.get("source_component", ""),
        "severity": payload.get("severity", "info"),
        "event_id": payload.get("event_id"),
        "span_id": payload.get("span_id"),
        "parent_span_id": payload.get("parent_span_id"),
        "ts": payload.get("ts"),
        "tags": tags,
    }


def get_context(trace: Any) -> dict[str, Any]:
    trace_dict = _as_dict(trace)
    context = trace_dict.get("context")
    if isinstance(context, dict):
        return context

    if any(k in trace_dict for k in ("sections", "evidence", "token_accounting", "flags")):
        return {
            "sections": trace_dict.get("sections", []),
            "evidence": trace_dict.get("evidence", []),
            "token_accounting": trace_dict.get("token_accounting", {}),
            "signals": trace_dict.get("flags", {}),
            "notes": [],
        }

    return {}


def get_sections(trace: Any) -> list[dict[str, Any]]:
    value = get_context(trace).get("sections", [])
    return value if isinstance(value, list) else []


def get_evidence(trace: Any) -> list[dict[str, Any]]:
    value = get_context(trace).get("evidence", [])
    return value if isinstance(value, list) else []


def get_token_accounting(trace: Any) -> dict[str, Any]:
    value = get_context(trace).get("token_accounting", {})
    return value if isinstance(value, dict) else {}


def get_signals(trace: Any) -> dict[str, Any]:
    value = get_context(trace).get("signals", {})
    return value if isinstance(value, dict) else {}


def get_notes(trace: Any) -> list[Any]:
    value = get_context(trace).get("notes", [])
    return value if isinstance(value, list) else []


def get_metrics(trace: Any) -> dict[str, Any]:
    trace_dict = _as_dict(trace)
    value = trace_dict.get("metrics", {})
    return value if isinstance(value, dict) else {}


def get_events(trace: Any) -> list[dict[str, Any]]:
    trace_dict = _as_dict(trace)
    value = trace_dict.get("events", [])
    if not isinstance(value, list):
        return []
    return [event for item in value if (event := _normalize_event(item))]


def get_turn(trace: Any) -> dict[str, Any]:
    trace_dict = _as_dict(trace)
    value = trace_dict.get("turn", {})
    return value if isinstance(value, dict) else {}


def get_final_prompt(trace: Any, *, fallback: str = "") -> str:
    for section in reversed(get_sections(trace)):
        if section.get("origin") == "prompt":
            text = section.get("text")
            if isinstance(text, str):
                return text
        if section.get("title") == "Final prompt":
            text = section.get("text")
            if isinstance(text, str):
                return text

    trace_dict = _as_dict(trace)
    value = trace_dict.get("final_prompt")
    if isinstance(value, str):
        return value

    return fallback


def get_retrieval_events(trace: Any) -> list[dict[str, Any]]:
    events = get_events(trace)
    return [
        event
        for event in events
        if (
            "rag" in event.get("tags", ())
            or "retrieval" in event.get("tags", ())
            or str(event.get("event_type", "")).startswith("retrieval_")
            or event.get("event_type") == "query_expanded"
        )
    ]


def get_retrieval_payload(trace: Any) -> dict[str, Any]:
    signals = get_signals(trace)
    payload = signals.get("retrieval_documents", {})
    return payload if isinstance(payload, dict) else {}


def get_retrieval_summary(trace: Any) -> dict[str, Any]:
    signals = get_signals(trace)
    summary = signals.get("retrieval_summary", {})
    return summary if isinstance(summary, dict) else {}


def get_agent_events(trace: Any) -> list[dict[str, Any]]:
    events = get_events(trace)
    return [
        event
        for event in events
        if (
            "agent" in event.get("tags", ())
            or str(event.get("event_type", "")).startswith("agent_")
            or str(event.get("source_package", "")) == "agent_lib"
        )
    ]


def get_agent_summary(trace: Any) -> dict[str, Any]:
    signals = get_signals(trace)
    summary = signals.get("agent_summary", {})
    return summary if isinstance(summary, dict) else {}


def get_agent_execution_summary(trace: Any) -> dict[str, Any]:
    summary = dict(get_agent_summary(trace))
    summary.setdefault("blocked_count", 0)
    summary.setdefault("degraded_count", 0)
    summary.setdefault("approval_count", 0)
    modes = summary.get("execution_modes")
    if isinstance(modes, list) and modes:
        return summary

    derived_modes: list[dict[str, Any]] = []
    for event in get_agent_events(trace):
        if event.get("event_type") != "agent_tool_result":
            continue
        payload = event.get("payload", {})
        tool_result = payload.get("tool_result", {}) if isinstance(payload, dict) else {}
        meta = tool_result.get("meta", {}) if isinstance(tool_result, dict) else {}
        if not isinstance(meta, dict):
            continue
        row = {
            "tool_name": tool_result.get("name"),
            "approval_required": bool(meta.get("approval_required", False)),
            "sandbox_requested_backend": meta.get("sandbox_requested_backend"),
            "sandbox_backend": meta.get("sandbox_backend"),
            "sandbox_external": bool(meta.get("sandbox_external", False)),
            "sandbox_fallback_used": bool(meta.get("sandbox_fallback_used", False)),
            "policy_reason": meta.get("policy_reason"),
            "returncode": meta.get("returncode"),
        }
        blocked_errors = {
            "policy_violation",
            "invalid_arguments",
            "invalid_path",
            "path_escape",
            "write_denied",
            "ownership_denied",
            "command_denied",
            "sandbox_unavailable",
            "invalid_sandbox_backend",
        }
        row["blocked"] = str(meta.get("error") or "") in blocked_errors
        row["degraded"] = bool(meta.get("sandbox_fallback_used"))
        derived_modes.append(row)

    if derived_modes:
        summary["execution_modes"] = derived_modes
        summary["blocked_count"] = sum(1 for row in derived_modes if row.get("blocked"))
        summary["degraded_count"] = sum(1 for row in derived_modes if row.get("degraded"))
        summary["approval_count"] = sum(1 for row in derived_modes if row.get("approval_required"))
    else:
        summary.setdefault("execution_modes", [])
    return summary


def get_agent_execution_rows(trace: Any) -> list[dict[str, Any]]:
    summary = get_agent_execution_summary(trace)
    rows = summary.get("execution_modes", [])
    return rows if isinstance(rows, list) else []
