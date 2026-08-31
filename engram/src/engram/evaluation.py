"""Adapters from Engram results to shared memory-evaluation observations."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from llm_harness_core import MemoryCaseObservation


def _evidence_id(item: Any) -> str | None:
    metadata = dict(
        (item.get("metadata") if isinstance(item, dict) else getattr(item, "metadata", None))
        or (item.get("meta") if isinstance(item, dict) else getattr(item, "meta", None))
        or {}
    )
    for key in ("evidence_id", "ledger_event_id", "memory_id", "episode_id"):
        value = metadata.get(key)
        if value:
            return str(value)
    for key in ("episode_id", "id"):
        value = item.get(key) if isinstance(item, dict) else getattr(item, key, None)
        if value:
            return str(value)
    return None


def observation_from_engram(
    *,
    stored_count: int,
    retrieved_items: Sequence[Any],
    prompt_result: Mapping[str, Any],
    observed_output: Mapping[str, Any] | None,
    inference_status: str = "completed",
    error_type: str | None = None,
) -> MemoryCaseObservation:
    """Create a staged observation using structured Engram provenance."""
    retrieved_ids = tuple(
        evidence_id for item in retrieved_items if (evidence_id := _evidence_id(item)) is not None
    )
    trace = prompt_result.get("trace")
    prompt_ids: list[str] = []
    for evidence in list(getattr(trace, "evidence", None) or []):
        evidence_id = _evidence_id(evidence)
        if evidence_id is not None and evidence_id not in prompt_ids:
            prompt_ids.append(evidence_id)
    diagnostics = {
        "budget": dict(prompt_result.get("budget_diagnostics") or {}),
        "retrieval": dict(prompt_result.get("retrieval_diagnostics") or {}),
        "prompt_tokens": prompt_result.get("prompt_tokens"),
        "memory_tokens": prompt_result.get("memory_tokens"),
        "compressed": bool(prompt_result.get("compressed", False)),
    }
    return MemoryCaseObservation(
        stored_count=int(stored_count),
        retrieved_evidence_ids=retrieved_ids,
        prompt_evidence_ids=tuple(prompt_ids),
        observed_output=dict(observed_output) if observed_output is not None else None,
        inference_status=inference_status,
        error_type=error_type,
        diagnostics=diagnostics,
    )


__all__ = ["observation_from_engram"]
