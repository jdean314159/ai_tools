from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Sequence

from llm_harness_core import (
    CapabilityDescriptor,
    CapabilityKind,
    MemoryRecord,
    OperationResult,
    TraceEvent,
)


def describe_language_tutor(
    *,
    language: str,
    memory_backend: str,
    strategy_name: str,
    features: Sequence[str] | None = None,
) -> CapabilityDescriptor:
    base_features = [
        "conversation",
        "session_planning",
        "memory_augmented_prompting",
        "drills",
        "session_summaries",
        f"memory_backend:{memory_backend}",
    ]
    if features:
        base_features.extend(features)
    return CapabilityDescriptor(
        kind=CapabilityKind.OTHER,
        provider="language_tutor",
        component="TutorSession",
        summary="Reference application and integration vehicle for ai_tools.",
        features=tuple(base_features),
        input_types=("tutor_session", "user_message", "language_profile"),
        output_types=("tutor_response", "session_plan", "trace_events", "memory_records"),
        metadata={
            "language": language,
            "memory_backend": memory_backend,
            "strategy": strategy_name,
        },
    )


def _to_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain(v) for v in value]
    if is_dataclass(value):
        return {k: _to_plain(v) for k, v in asdict(value).items()}
    if hasattr(value, "model_dump"):
        return _to_plain(value.model_dump())
    if hasattr(value, "__dict__"):
        return {k: _to_plain(v) for k, v in vars(value).items() if not k.startswith("_")}
    return str(value)


def recent_turns_to_records(turns: Iterable[Any], *, source: str = "language_tutor.working_memory") -> tuple[MemoryRecord, ...]:
    records: list[MemoryRecord] = []
    for idx, turn in enumerate(turns):
        role = getattr(turn, "role", "unknown")
        content = getattr(turn, "content", None) or getattr(turn, "text", None) or str(turn)
        metadata = {
            "role": role,
            "timestamp": getattr(turn, "timestamp", None),
            "session_id": getattr(turn, "session_id", None),
            "turn_index": idx,
        }
        record_id = getattr(turn, "turn_id", None) or getattr(turn, "id", None)
        records.append(MemoryRecord(text=str(content), source=source, record_id=record_id, metadata=_to_plain(metadata)))
    return tuple(records)


def session_trace_events(
    *,
    session: Any,
    event_type: str,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    severity: str = "info",
    tags: Sequence[str] = (),
) -> tuple[TraceEvent, ...]:
    base_payload = {
        "session_id": getattr(session, "session_id", None),
        "language": getattr(session, "language", None),
        "memory_backend": getattr(session, "memory_backend", None),
        "state": getattr(getattr(session, "state", None), "value", None),
        "strategy": getattr(session, "strategy", {}).get("name") if getattr(session, "strategy", None) else None,
        "exchange_count": getattr(session, "exchange_count", None),
    }
    if payload:
        base_payload.update(_to_plain(payload))
    return (
        TraceEvent(
            event_type=event_type,
            source_package="language_tutor",
            source_component="TutorSession",
            payload=base_payload,
            severity=severity,
            message=message,
            tags=tuple(tags),
        ),
    )


def start_result_to_interop_result(session: Any, result: dict[str, Any]) -> OperationResult[dict[str, Any]]:
    warnings = ()
    diagnostics = {
        "trace_events": session_trace_events(
            session=session,
            event_type="language_tutor.session.started",
            message="Tutor session started.",
            payload={
                "plan_present": bool(result.get("plan")),
                "greeting": result.get("greeting"),
            },
            tags=("language_tutor", "session", "start"),
        ),
        "memory_records": recent_turns_to_records(session.memory.get_recent_turns(n=5)),
        "capability": describe_language_tutor(
            language=session.language,
            memory_backend=session.memory_backend,
            strategy_name=session.strategy.get("name", "unknown"),
        ),
    }
    return OperationResult.success(_to_plain(result), warnings=warnings, diagnostics=diagnostics)


def tutor_response_to_interop_result(session: Any, response: Any, *, user_message: str | None = None) -> OperationResult[dict[str, Any]]:
    metadata = _to_plain(getattr(response, "metadata", None) or {})
    payload = {
        "user_message": user_message,
        "response_text": getattr(response, "text", None),
        "corrections_count": len(getattr(response, "corrections", None) or []),
        "new_vocabulary_count": len(getattr(response, "new_vocabulary", None) or []),
        "prompt_tokens": metadata.get("prompt_tokens"),
        "memory_tokens": metadata.get("memory_tokens"),
        "compressed": metadata.get("compressed"),
    }
    diagnostics = {
        "trace_events": session_trace_events(
            session=session,
            event_type="language_tutor.turn.completed",
            message="Tutor turn completed.",
            payload=payload,
            tags=("language_tutor", "conversation", "response"),
        ),
        "memory_records": recent_turns_to_records(session.memory.get_recent_turns(n=8)),
        "capability": describe_language_tutor(
            language=session.language,
            memory_backend=session.memory_backend,
            strategy_name=session.strategy.get("name", "unknown"),
        ),
    }
    value = {
        "text": getattr(response, "text", ""),
        "corrections": _to_plain(getattr(response, "corrections", None) or []),
        "new_vocabulary": _to_plain(getattr(response, "new_vocabulary", None) or []),
        "metadata": metadata,
    }
    return OperationResult.success(value, diagnostics=diagnostics)


def explanation_to_interop_result(session: Any, *, text: str, question: str | None, explanation: str) -> OperationResult[dict[str, Any]]:
    diagnostics = {
        "trace_events": session_trace_events(
            session=session,
            event_type="language_tutor.explanation.completed",
            message="Grammar explanation completed.",
            payload={"text": text, "question": question},
            tags=("language_tutor", "explanation"),
        ),
        "memory_records": recent_turns_to_records(session.memory.get_recent_turns(n=5)),
        "capability": describe_language_tutor(
            language=session.language,
            memory_backend=session.memory_backend,
            strategy_name=session.strategy.get("name", "unknown"),
            features=("grammar_explanations",),
        ),
    }
    return OperationResult.success({"text": text, "question": question, "explanation": explanation}, diagnostics=diagnostics)
