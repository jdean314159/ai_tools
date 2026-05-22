from __future__ import annotations

from typing import Any

from llm_harness_core import CapabilityDescriptor, CapabilityKind, MemoryRecord

from .contracts import AugmentResult
from .inspection import PromptBuildTrace


def describe_memory(memory: Any) -> CapabilityDescriptor:
    metadata = {
        "project_id": getattr(memory, "project_id", "default"),
        "session_id": getattr(memory, "session_id", None),
        "has_retriever": getattr(memory, "retriever", None) is not None,
        "auto_ingest_turns": getattr(getattr(memory, "_quality", None), "auto_ingest_turns", False),
        "auto_ingest_roles": list(getattr(getattr(memory, "_quality", None), "auto_ingest_roles", ())),
        "assistant_memory_kinds": list(getattr(getattr(memory, "_quality", None), "assistant_memory_kinds", ())),
        "supports_canonical_updates": True,
    }
    return CapabilityDescriptor(
        kind=CapabilityKind.MEMORY,
        provider="engram",
        component=memory.__class__.__name__,
        version="0.1.0",
        summary="Prompt augmentation with lightweight user-preferred memory hygiene, canonical updates, and retrieval.",
        features=("prompt_augmentation", "working_memory", "episodic_memory", "trace_events", "lightweight_ingestion", "user_preferred_ingestion", "deduped_retrieval", "canonical_updates"),
        input_types=("llm_message", "augment_request"),
        output_types=("prompt", "operation_result", "trace_event[]"),
        metadata=metadata,
    )


def trace_to_memory_records(trace: PromptBuildTrace) -> list[MemoryRecord]:
    return [item.to_memory_record() for item in trace.evidence]


def augment_result_to_interop_result(result: AugmentResult):
    return result.to_interop_result()
