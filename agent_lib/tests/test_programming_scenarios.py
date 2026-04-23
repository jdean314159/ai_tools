from __future__ import annotations

from pathlib import Path

from agent_lib.examples.programming_evaluation import (
    build_default_benchmark_scenarios,
    run_programming_scenario_benchmark,
)


def test_default_benchmark_scenarios_cover_memory_and_runtime_variants() -> None:
    scenarios = build_default_benchmark_scenarios()
    names = {scenario.name for scenario in scenarios}
    assert {
        "engram_lite_minimum_reliable",
        "engram_minimum_reliable",
        "engram_lite_isolated_workspace",
    }.issubset(names)


def test_programming_scenario_benchmark_produces_case_matrix(tmp_path: Path) -> None:
    report = run_programming_scenario_benchmark(root=tmp_path)
    payload = report.to_dict()
    assert payload["total_scenarios"] >= 3
    assert len(payload["scenarios"]) == payload["total_scenarios"]
    assert payload["case_matrix"]
    first = payload["case_matrix"][0]
    assert "case_name" in first
    assert "scenarios" in first
    scenario_names = set(payload["scenario_names"])
    assert scenario_names.issubset(set(first["scenarios"].keys()) | scenario_names)


def test_scenario_summaries_include_memory_backend_and_profile(tmp_path: Path) -> None:
    report = run_programming_scenario_benchmark(root=tmp_path)
    payload = report.to_dict()
    first = payload["scenarios"][0]
    assert {"name", "memory_backend", "runtime_profile", "summary", "comparison"}.issubset(first)
