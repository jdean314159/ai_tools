"""Dependency-free, stage-attributed memory reliability evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


MEMORY_STAGES = ("storage", "retrieval", "composition", "inference", "scoring")


@dataclass(frozen=True)
class MemoryCaseSpec:
    case_id: str
    expected_storage_count: int
    required_evidence_ids: tuple[str, ...]
    expected_output: Mapping[str, Any]
    forbidden_evidence_ids: tuple[str, ...] = ()
    forbidden_retrieval_ids: tuple[str, ...] = ()
    forbidden_prompt_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryCaseObservation:
    stored_count: int
    retrieved_evidence_ids: tuple[str, ...]
    prompt_evidence_ids: tuple[str, ...]
    observed_output: Mapping[str, Any] | None
    inference_status: str = "completed"
    error_type: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryCaseEvaluation:
    case_id: str
    storage_passed: bool
    retrieval_passed: bool
    composition_passed: bool
    inference_passed: bool
    scoring_passed: bool
    end_to_end_passed: bool
    primary_failure_stage: str | None
    issue_codes: tuple[str, ...]
    missing_retrieval_ids: tuple[str, ...]
    forbidden_retrieval_ids: tuple[str, ...]
    missing_prompt_ids: tuple[str, ...]
    forbidden_prompt_ids: tuple[str, ...]
    mismatched_output_fields: tuple[str, ...]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _missing(required: Sequence[str], observed: Sequence[str]) -> tuple[str, ...]:
    observed_set = set(observed)
    return tuple(item for item in required if item not in observed_set)


def _present(forbidden: Sequence[str], observed: Sequence[str]) -> tuple[str, ...]:
    observed_set = set(observed)
    return tuple(item for item in forbidden if item in observed_set)


def evaluate_memory_case(
    spec: MemoryCaseSpec,
    observation: MemoryCaseObservation,
) -> MemoryCaseEvaluation:
    """Attribute a deterministic memory case without an LLM judge."""
    storage_passed = observation.stored_count == spec.expected_storage_count
    missing_retrieval = _missing(spec.required_evidence_ids, observation.retrieved_evidence_ids)
    forbidden_retrieval = _present(
        spec.forbidden_evidence_ids + spec.forbidden_retrieval_ids,
        observation.retrieved_evidence_ids,
    )
    retrieval_passed = not missing_retrieval and not forbidden_retrieval
    missing_prompt = _missing(spec.required_evidence_ids, observation.prompt_evidence_ids)
    forbidden_prompt = _present(
        spec.forbidden_evidence_ids + spec.forbidden_prompt_ids,
        observation.prompt_evidence_ids,
    )
    composition_passed = not missing_prompt and not forbidden_prompt
    inference_passed = (
        observation.inference_status == "completed" and observation.observed_output is not None
    )
    observed_output = dict(observation.observed_output or {})
    mismatched_fields = tuple(
        key
        for key, expected in spec.expected_output.items()
        if key not in observed_output or observed_output[key] != expected
    )
    scoring_passed = inference_passed and not mismatched_fields

    issues: list[str] = []
    if not storage_passed:
        issues.append("storage_count_mismatch")
    if missing_retrieval:
        issues.append("retrieval_missing_required_evidence")
    if forbidden_retrieval:
        issues.append("retrieval_selected_forbidden_evidence")
    if missing_prompt:
        issues.append("composition_missing_required_evidence")
    if forbidden_prompt:
        issues.append("composition_included_forbidden_evidence")
    if not inference_passed:
        issues.append("inference_failed")
    elif mismatched_fields:
        issues.append("output_mismatch")

    stage_passes = {
        "storage": storage_passed,
        "retrieval": retrieval_passed,
        "composition": composition_passed,
        "inference": inference_passed,
        "scoring": scoring_passed,
    }
    primary_failure = next((stage for stage in MEMORY_STAGES if not stage_passes[stage]), None)
    end_to_end = all(stage_passes.values())
    return MemoryCaseEvaluation(
        case_id=spec.case_id,
        storage_passed=storage_passed,
        retrieval_passed=retrieval_passed,
        composition_passed=composition_passed,
        inference_passed=inference_passed,
        scoring_passed=scoring_passed,
        end_to_end_passed=end_to_end,
        primary_failure_stage=primary_failure,
        issue_codes=tuple(issues),
        missing_retrieval_ids=missing_retrieval,
        forbidden_retrieval_ids=forbidden_retrieval,
        missing_prompt_ids=missing_prompt,
        forbidden_prompt_ids=forbidden_prompt,
        mismatched_output_fields=mismatched_fields,
        diagnostics=dict(observation.diagnostics),
    )


def summarize_memory_evaluations(
    evaluations: Sequence[MemoryCaseEvaluation],
) -> dict[str, Any]:
    items = list(evaluations)
    by_stage = {stage: 0 for stage in MEMORY_STAGES}
    issue_counts: dict[str, int] = {}
    for item in items:
        if item.primary_failure_stage:
            by_stage[item.primary_failure_stage] += 1
        for issue in item.issue_codes:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
    return {
        "case_count": len(items),
        "end_to_end_pass_count": sum(item.end_to_end_passed for item in items),
        "stage_pass_counts": {
            "storage": sum(item.storage_passed for item in items),
            "retrieval": sum(item.retrieval_passed for item in items),
            "composition": sum(item.composition_passed for item in items),
            "inference": sum(item.inference_passed for item in items),
            "scoring": sum(item.scoring_passed for item in items),
        },
        "primary_failure_counts": by_stage,
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def build_memory_experiment_body(
    *,
    profile: str,
    profile_version: int,
    evaluations: Sequence[MemoryCaseEvaluation],
    retain_diagnostics: bool = True,
) -> dict[str, Any]:
    """Build a privacy-minimized body; raw prompts, memories, and outputs are absent."""
    items = []
    for evaluation in evaluations:
        encoded = evaluation.to_dict()
        if not retain_diagnostics:
            encoded["diagnostics"] = {}
        items.append(encoded)
    return {
        "schema_version": 1,
        "profile": profile,
        "profile_version": int(profile_version),
        "oracle_or_llm_judge_used": False,
        "summary": summarize_memory_evaluations(evaluations),
        "evaluations": items,
        "privacy": {
            "raw_prompts_retained": False,
            "raw_memories_retained": False,
            "raw_outputs_retained": False,
        },
    }


def prepare_new_artifact_path(path: str | Path) -> Path:
    """Create the parent and refuse to overwrite a governed experiment artifact."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"artifact already exists: {target}")
    return target


__all__ = [
    "MEMORY_STAGES",
    "MemoryCaseSpec",
    "MemoryCaseObservation",
    "MemoryCaseEvaluation",
    "evaluate_memory_case",
    "summarize_memory_evaluations",
    "build_memory_experiment_body",
    "prepare_new_artifact_path",
]
