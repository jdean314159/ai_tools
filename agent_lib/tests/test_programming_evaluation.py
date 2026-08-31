from __future__ import annotations

from pathlib import Path

from agent_lib.examples.programming_evaluation import (
    build_representative_programming_cases,
    run_programming_benchmark,
)
from agent_lib.examples.programming_task import build_minimum_reliable_programming_config


def test_build_representative_programming_cases_has_expected_coverage() -> None:
    cases = build_representative_programming_cases()
    names = {case.name for case in cases}
    assert {
        "minimal_reliable_auto_fix",
        "proposal_only_review_gate",
        "nested_path_with_compile_check",
        "resume_after_partial_run",
        "isolated_workspace_fix",
    }.issubset(names)


def test_programming_benchmark_report_passes_representative_cases(tmp_path: Path) -> None:
    report = run_programming_benchmark(root=tmp_path)
    assert report.total >= 5
    assert report.failed == 0
    results = {item.case_name: item for item in report.results}
    assert results["proposal_only_review_gate"].patch_status == "proposed"
    assert results["resume_after_partial_run"].status == "completed"
    assert results["isolated_workspace_fix"].verification_success is True


def test_minimum_reliable_config_turns_off_optional_parallelism() -> None:
    config = build_minimum_reliable_programming_config()
    assert config.task.workspace.max_parallel_patch_workers == 1
    assert config.task.workspace.approval_mode == "auto"
    assert config.task.workspace.isolation_mode == "in_place"


def test_programming_benchmark_report_includes_summary_metrics(tmp_path: Path) -> None:
    report = run_programming_benchmark(root=tmp_path)
    payload = report.to_dict()
    assert "summary" in payload
    assert payload["summary"]["average_steps"] >= 0
    assert payload["summary"]["total_verifications"] >= len(payload["results"])
    assert "comparison" in payload
    first = payload["comparison"][0]
    assert {
        "case_name",
        "steps",
        "retries",
        "escalations",
        "verification_outcome",
        "patch_status",
        "elapsed_seconds",
    }.issubset(first)
