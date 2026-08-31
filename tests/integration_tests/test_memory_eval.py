from __future__ import annotations

from integration_tests.memory_eval import run_memory_eval, run_memory_eval_suite


class _StubAnswerClient:
    def answer(self, prompt: str, *, question: str | None = None) -> str:
        lowered = prompt.lower()
        if "qwen3:32b" in lowered:
            return "qwen3:32b"
        if "us-west-2" in lowered:
            return "us-west-2"
        if "wednesday at 2 pm" in lowered or ("wednesday" in lowered and "2 pm" in lowered):
            return "Wednesday at 2 PM."
        if "duckdb" in lowered:
            return "DuckDB"
        if "markdown" in lowered and "repo" in lowered:
            return "Markdown files committed to the repo."
        if "python" in lowered:
            return "Python"
        if "docker" in lowered:
            return "Docker"
        return "I do not know."


def _probe_map(report: dict, backend: str) -> dict[str, dict]:
    return {item["probe"]: item for item in report["backends"][backend]["probe_results"]}


def test_memory_eval_harness_runs_for_both_backends() -> None:
    report = run_memory_eval()

    assert set(report["backends"]) == {"basic", "full"}
    assert report["backends"]["basic"]["summary"]["signal_retention_rate"] >= 0.5
    assert report["backends"]["full"]["summary"]["signal_retention_rate"] >= 0.5


def test_basic_config_cold_eval_still_rejects_seeded_noise() -> None:
    report = run_memory_eval()
    basic_probes = _probe_map(report, "basic")

    assert basic_probes["ephemeral_rejection"]["passed"] is True
    assert basic_probes["assistant_chatter_rejection"]["passed"] is True


def test_full_config_cold_eval_supports_signal_and_paraphrase_probes() -> None:
    report = run_memory_eval()
    full = report["backends"]["full"]
    probes = _probe_map(report, "full")

    assert probes["preference_recall"]["passed"] is True
    assert probes["preference_paraphrase"]["passed"] is True
    assert full["summary"]["noise_rejection_rate"] >= 0.5
    assert full["summary"]["paraphrase_retention_rate"] >= 0.5


def test_memory_eval_summary_reports_extended_rates_and_probe_categories() -> None:
    report = run_memory_eval()
    expected_categories = {"signal", "paraphrase", "decoy", "update", "noise"}

    for backend in ("basic", "full"):
        summary = report["backends"][backend]["summary"]
        for key in (
            "paraphrase_retention_rate",
            "decoy_rejection_rate",
            "update_resolution_rate",
            "noise_rejection_rate",
            "answer_baseline_pass_rate",
            "answer_memory_pass_rate",
            "answer_net_uplift",
        ):
            assert key in summary
            value = summary[key]
            assert value is None or -1.0 <= value <= 1.0

        categories = {item["category"] for item in report["backends"][backend]["probe_results"]}
        assert expected_categories.issubset(categories)


def test_full_config_cold_eval_handles_decoy_and_update_probes() -> None:
    report = run_memory_eval()
    probes = _probe_map(report, "full")

    assert probes["decision_decoy"]["passed"] is True
    assert probes["update_resolution"]["passed"] is True


def test_basic_config_cold_eval_handles_decoy_and_update_probes() -> None:
    report = run_memory_eval()
    probes = _probe_map(report, "basic")

    assert probes["decision_decoy"]["passed"] is True
    assert probes["update_resolution"]["passed"] is True


def test_memory_eval_suite_runs_default_and_stress_scenarios() -> None:
    suite = run_memory_eval_suite()

    assert suite["answer_eval_enabled"] is False
    assert {item["name"] for item in suite["scenarios"]} == {
        "default_memory_quality",
        "stress_memory_quality",
    }
    assert set(suite["results"]) == {"default_memory_quality", "stress_memory_quality"}
    for backend in ("basic", "full"):
        assert suite["aggregate"][backend]["probe_pass_rate"] >= 0.5


def test_memory_eval_optional_answer_uplift_path_reports_memory_improvement() -> None:
    report = run_memory_eval("stress", answer_client=_StubAnswerClient())

    for backend in ("basic", "full"):
        summary = report["backends"][backend]["summary"]
        assert summary["answer_baseline_pass_rate"] is not None
        assert summary["answer_memory_pass_rate"] is not None
        assert summary["answer_memory_pass_rate"] >= summary["answer_baseline_pass_rate"]
        assert summary["answer_positive_uplift_rate"] is not None


def test_score_text_against_probe_uses_shared_evaluator() -> None:
    from integration_tests.memory_eval import MemoryProbe, _score_text_against_probe

    probe = MemoryProbe(
        name="pref",
        query="preferred language",
        expected_substrings=("python",),
        forbidden_substrings=("java",),
        question="What language?",
    )
    score = _score_text_against_probe("Python is preferred.", probe)
    assert score["passed"] is True
    assert score["evaluator"] == "substring_match"
    assert score["score"] >= 1.0


def test_answer_eval_records_shared_evaluator_metadata() -> None:
    report = run_memory_eval("default", answer_client=_StubAnswerClient())

    for backend in ("basic", "full"):
        probe = _probe_map(report, backend)["preference_recall"]
        answer_eval = probe["answer_eval"]
        assert answer_eval["evaluator"] == "substring_match"
        assert answer_eval["memory_score"] is not None
        assert answer_eval["baseline_score"] is not None
        assert answer_eval["memory_rationale"]
