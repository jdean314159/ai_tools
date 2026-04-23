from __future__ import annotations

from typing import Any

from llm_harness_core import (
    CapabilityDescriptor,
    CapabilityKind,
    MemoryRecord,
    OperationResult,
    TraceEvent,
)

from .inspection import PromptBuildTrace


def describe_memory(memory: Any) -> CapabilityDescriptor:
    metadata = {
        "project_id": getattr(memory, "project_id", None),
        "session_id": getattr(memory, "session_id", None),
        "project_type": getattr(getattr(memory, "project_type", None), "value", getattr(memory, "project_type", None)),
        "supports_working_memory": getattr(memory, "working", None) is not None,
        "supports_episodic_memory": getattr(memory, "episodic", None) is not None,
        "supports_semantic_memory": getattr(memory, "semantic", None) is not None,
        "supports_cold_storage": getattr(memory, "cold", None) is not None,
        "supports_canonical_updates": True,
        "supports_trace_events": True,
    }
    return CapabilityDescriptor(
        kind=CapabilityKind.MEMORY,
        provider="engram",
        component=memory.__class__.__name__,
        version="0.1.19",
        summary="Layered prompt augmentation with working, episodic, semantic, and cold memory plus prompt-build inspection.",
        features=(
            "prompt_augmentation",
            "working_memory",
            "episodic_memory",
            "semantic_memory",
            "cold_storage",
            "trace_events",
            "prompt_build_trace",
            "canonical_updates",
        ),
        input_types=("llm_message", "user_prompt"),
        output_types=("prompt", "operation_result", "trace_event[]", "memory_record[]"),
        metadata=metadata,
    )


def trace_to_memory_records(trace: PromptBuildTrace) -> list[MemoryRecord]:
    records: list[MemoryRecord] = []
    for idx, evidence in enumerate(trace.evidence):
        meta = dict(getattr(evidence, "meta", {}) or {})
        meta.setdefault("evidence_index", idx)
        meta.setdefault("transformation_stage", "prompt_build_trace")
        if evidence.score is not None:
            meta.setdefault("score", evidence.score)
        records.append(
            MemoryRecord(
                text=evidence.text,
                source=evidence.source,
                record_id=meta.get("record_id") or meta.get("id"),
                score=evidence.score,
                metadata=meta,
            )
        )
    return records


def trace_to_interop_events(trace: PromptBuildTrace) -> list[TraceEvent]:
    events: list[TraceEvent] = [
        TraceEvent(
            event_type="prompt_build_completed",
            source_package="engram",
            source_component="ProjectMemory",
            payload={
                "section_count": len(trace.sections),
                "evidence_count": len(trace.evidence),
                "compressed": trace.token_accounting.compressed,
                "truncated": trace.token_accounting.truncated,
                "target_tokens": trace.token_accounting.target_tokens,
                "total_tokens": trace.token_accounting.total_tokens,
                "flags": dict(trace.flags),
            },
            message="Prompt build finished.",
            tags=("prompt", "memory"),
        )
    ]
    for idx, section in enumerate(trace.sections):
        events.append(
            TraceEvent(
                event_type="prompt_section_rendered",
                source_package="engram",
                source_component="ProjectMemory",
                payload={
                    "section_index": idx,
                    "title": section.title,
                    "origin": section.origin,
                    "tokens": section.tokens,
                    "metadata": dict(getattr(section, "meta", {}) or {}),
                },
                message=f"Rendered prompt section: {section.title}",
                tags=("prompt", section.origin),
            )
        )
    for idx, evidence in enumerate(trace.evidence):
        events.append(
            TraceEvent(
                event_type="memory_evidence_included",
                source_package="engram",
                source_component="ProjectMemory",
                payload={
                    "evidence_index": idx,
                    "source": evidence.source,
                    "text": evidence.text,
                    "score": evidence.score,
                    "metadata": dict(getattr(evidence, "meta", {}) or {}),
                    "record_id": (dict(getattr(evidence, "meta", {}) or {}).get("record_id") or dict(getattr(evidence, "meta", {}) or {}).get("id")),
                    "provenance": {
                        "origin": evidence.source,
                        "record_id": (dict(getattr(evidence, "meta", {}) or {}).get("record_id") or dict(getattr(evidence, "meta", {}) or {}).get("id")),
                        "session_id": dict(getattr(evidence, "meta", {}) or {}).get("session_id"),
                        "project_id": dict(getattr(evidence, "meta", {}) or {}).get("project_id"),
                        "memory_type": dict(getattr(evidence, "meta", {}) or {}).get("memory_type") or dict(getattr(evidence, "meta", {}) or {}).get("kind"),
                    },
                    "transformations": ("retrieved", "normalized", "prompt_included"),
                },
                message=f"Included {evidence.source} memory evidence.",
                tags=("memory", evidence.source),
            )
        )
    return events


def prompt_result_to_interop_result(result: dict[str, Any], trace: PromptBuildTrace) -> OperationResult[str]:
    diagnostics = {
        "prompt_tokens": result.get("prompt_tokens"),
        "memory_tokens": result.get("memory_tokens"),
        "compressed": bool(result.get("compressed", False)),
        "trace": trace,
        "trace_events": trace_to_interop_events(trace),
        "memory_records": trace_to_memory_records(trace),
        "raw_context": result.get("context"),
    }
    return OperationResult.success(result.get("prompt", ""), diagnostics=diagnostics)


def response_to_interop_result(response: dict[str, Any], trace: PromptBuildTrace) -> OperationResult[str]:
    diagnostics = {
        "prompt": response.get("prompt"),
        "prompt_tokens": response.get("prompt_tokens"),
        "memory_tokens": response.get("memory_tokens"),
        "compressed": bool(response.get("compressed", False)),
        "strategy": response.get("strategy"),
        "run_id": response.get("run_id"),
        "trace": trace,
        "trace_events": trace_to_interop_events(trace),
        "memory_records": trace_to_memory_records(trace),
    }
    return OperationResult.success(response.get("answer", ""), diagnostics=diagnostics)
