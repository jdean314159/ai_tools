from __future__ import annotations

import pytest

from llm_harness_core import (
    MemoryCaseObservation,
    MemoryCaseSpec,
    build_memory_experiment_body,
    evaluate_memory_case,
    prepare_new_artifact_path,
    summarize_memory_evaluations,
)


SPEC = MemoryCaseSpec(
    case_id="update",
    expected_storage_count=2,
    required_evidence_ids=("current",),
    forbidden_evidence_ids=("obsolete",),
    expected_output={"value": "new", "evidence_id": "current"},
)


def test_attributes_first_failure_and_all_issue_codes():
    result = evaluate_memory_case(SPEC, MemoryCaseObservation(
        stored_count=2,
        retrieved_evidence_ids=("obsolete",),
        prompt_evidence_ids=("obsolete",),
        observed_output={"value": "old", "evidence_id": "obsolete"},
        diagnostics={"memory_starved": False},
    ))
    assert result.primary_failure_stage == "retrieval"
    assert result.issue_codes == (
        "retrieval_missing_required_evidence", "retrieval_selected_forbidden_evidence",
        "composition_missing_required_evidence", "composition_included_forbidden_evidence",
        "output_mismatch",
    )
    assert result.mismatched_output_fields == ("value", "evidence_id")


def test_distinguishes_composition_from_retrieval_failure():
    composition_spec = MemoryCaseSpec(
        case_id="composition", expected_storage_count=2,
        required_evidence_ids=("current",), forbidden_prompt_ids=("obsolete",),
        expected_output={"value": "new", "evidence_id": "current"},
    )
    result = evaluate_memory_case(composition_spec, MemoryCaseObservation(
        stored_count=2,
        retrieved_evidence_ids=("current", "obsolete"),
        prompt_evidence_ids=("current", "obsolete"),
        observed_output={"value": "new", "evidence_id": "current"},
    ))
    assert result.retrieval_passed is True
    assert result.composition_passed is False
    assert result.primary_failure_stage == "composition"


def test_summary_and_body_are_privacy_minimized():
    passed = evaluate_memory_case(SPEC, MemoryCaseObservation(
        stored_count=2, retrieved_evidence_ids=("current",), prompt_evidence_ids=("current",),
        observed_output={"value": "new", "evidence_id": "current"},
    ))
    summary = summarize_memory_evaluations([passed])
    body = build_memory_experiment_body(profile="test.memory", profile_version=1, evaluations=[passed])
    assert summary["end_to_end_pass_count"] == 1
    assert body["oracle_or_llm_judge_used"] is False
    assert body["privacy"] == {
        "raw_prompts_retained": False, "raw_memories_retained": False, "raw_outputs_retained": False,
    }
    assert "observed_output" not in str(body)


def test_prepare_artifact_path_refuses_overwrite(tmp_path):
    target = prepare_new_artifact_path(tmp_path / "nested" / "run.json")
    assert target.parent.is_dir()
    target.write_text("{}")
    with pytest.raises(FileExistsError):
        prepare_new_artifact_path(target)
