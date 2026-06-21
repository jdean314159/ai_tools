from __future__ import annotations

import json
from pathlib import Path

import pytest

from diagnostics_agent import (
    ConcernAssessment,
    Interpretation,
    InterpreterError,
    LogInterpreter,
    LogTriage,
)
from diagnostics_agent.eval import CaseScore, aggregate, render_report, score_case
from llm_engines import get_engine
from llm_engines.contracts import BackendUnavailableError, ModelNotFoundError


FP_RATE_MAX = 0.10
RECALL_MIN = 0.90
# Initial Phase 3 gate values. Tighten these as the labeled corpus grows.

CORPUS = Path(__file__).parent / "fixtures" / "eval"


def test_clean_pass_has_zero_fp_and_full_recall() -> None:
    score = _score(
        concerns=[("auth", "medium")],
        expected=[("noise", "excluded", False), ("auth", "medium", False)],
    )

    report = aggregate([score])

    assert report.fp_rate == 0.0
    assert report.recall == 1.0
    assert report.band_accuracy == 1.0


def test_excluded_concern_is_false_positive() -> None:
    score = _score(
        concerns=[("noise", "medium")],
        expected=[("noise", "excluded", False)],
    )

    report = aggregate([score])

    assert score.concern_scores[0].outcome == "false_positive"
    assert score.concern_scores[0].band_delta == 2
    assert report.fp_rate == 1.0


def test_missing_high_concern_is_miss() -> None:
    score = _score(concerns=[], expected=[("disk", "high", False)])

    report = aggregate([score])

    assert score.concern_scores[0].outcome == "miss"
    assert score.concern_scores[0].band_delta == -3
    assert report.fp_rate is None
    assert report.recall == 0.0
    assert report.band_accuracy is None


def test_wrong_band_is_miscalibrated() -> None:
    score = _score(
        concerns=[("service", "critical")],
        expected=[("service", "low", False)],
    )

    report = aggregate([score])

    assert score.concern_scores[0].outcome == "miscalibrated"
    assert score.concern_scores[0].band_delta == 2
    assert report.recall == 1.0
    assert report.band_accuracy == 0.0


def test_interpretation_failure_scores_misses_and_clean_exclusions() -> None:
    labels = _labels(
        [("noise", "excluded", False), ("oom", "high", False)]
    )

    score = score_case(None, LogTriage().triage(""), labels)

    assert [item.outcome for item in score.concern_scores] == ["ok", "miss"]
    assert score.overall_security_ok is False
    assert score.overall_operational_ok is False


def test_known_gap_is_reported_but_excluded_from_aggregates() -> None:
    score = _score(
        concerns=[("disk_io_error", "high")],
        expected=[("disk_io_error", "low", True)],
    )

    report = aggregate([score])

    assert score.concern_scores[0].known_gap is True
    assert score.concern_scores[0].outcome == "miscalibrated"
    assert report.counts == {}
    assert report.fp_rate is None
    assert report.recall is None
    assert report.band_accuracy is None


def test_all_excluded_metrics_render_undefined_ratios_as_na() -> None:
    score = _score(
        concerns=[],
        expected=[
            ("acpi_ae_already_exists", "excluded", False),
            ("ata_drm_info", "excluded", False),
        ],
    )

    report = aggregate([score])
    output = render_report(report, {})

    assert report.fp_rate == 0.0
    assert report.recall is None
    assert report.band_accuracy is None
    assert "fp_rate:       0.000" in output
    assert "recall:        n/a" in output
    assert "band_accuracy: n/a" in output


def test_unexpected_concern_counts_as_false_positive() -> None:
    score = _score(
        concerns=[("auth", "medium"), ("invented", "high")],
        expected=[("auth", "medium", False)],
    )

    report = aggregate([score])

    assert score.unexpected_concerns == ("invented",)
    assert report.fp_rate == 1.0
    assert report.counts["unexpected_concern"] == 1


@pytest.mark.ollama
def test_live_fp_gate(pytestconfig: pytest.Config) -> None:
    model = pytestconfig.getoption("--gate-model")
    base_url = pytestconfig.getoption("--gate-base-url")
    kwargs = {"base_url": base_url} if base_url else {}
    try:
        engine = get_engine("ollama", model, **kwargs)
    except (BackendUnavailableError, ModelNotFoundError) as exc:
        pytest.skip(f"Ollama gate backend unavailable: {exc}")

    triage = LogTriage()
    interpreter = LogInterpreter(engine, allow_remote=bool(base_url))
    scores = []
    errors = {}
    for labels_path in sorted(CORPUS.glob("*.labels.json")):
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        log_path = labels_path.with_name(
            labels_path.name.removesuffix(".labels.json") + ".log"
        )
        summary = triage.triage(log_path.read_text(encoding="utf-8"))
        interpretation = None
        try:
            interpretation = interpreter.interpret(summary, system_facts=None)
        except InterpreterError as exc:
            errors[labels["case"]] = str(exc)
        scores.append(score_case(interpretation, summary, labels))

    report = aggregate(scores)
    offenders = _offending_rows(report.case_scores)
    detail = "\n".join(
        [*offenders, *(f"{case}: {error}" for case, error in errors.items())]
    )
    if report.fp_rate is not None:
        assert report.fp_rate <= FP_RATE_MAX, (
            f"false-positive gate failed: {report.fp_rate:.3f} > "
            f"{FP_RATE_MAX:.3f}\n{detail}"
        )
    if report.recall is not None:
        assert report.recall >= RECALL_MIN, (
            f"recall gate failed: {report.recall:.3f} < "
            f"{RECALL_MIN:.3f}\n{detail}"
        )


def _score(
    *,
    concerns: list[tuple[str, str]],
    expected: list[tuple[str, str, bool]],
) -> CaseScore:
    return score_case(
        _interpretation(concerns),
        LogTriage().triage(""),
        _labels(expected),
    )


def _interpretation(concerns: list[tuple[str, str]]) -> Interpretation:
    return Interpretation(
        reasoning="Evaluation fixture.",
        summary="Evaluation fixture.",
        security_risk="none",
        operational_risk="low",
        prioritized_concerns=[
            ConcernAssessment(
                finding_ref=finding_ref,
                rationale="Evaluation fixture.",
                severity=severity,
            )
            for finding_ref, severity in concerns
        ],
        recommended_checks=[],
    )


def _labels(expected: list[tuple[str, str, bool]]) -> dict:
    return {
        "case": "unit",
        "expected_overall": {
            "security_risk": "none",
            "operational_risk": "low",
        },
        "expected_concerns": [
            {
                "finding_ref": finding_ref,
                "expected_band": expected_band,
                "known_gap": known_gap,
            }
            for finding_ref, expected_band, known_gap in expected
        ],
    }


def _offending_rows(case_scores: tuple[CaseScore, ...]) -> list[str]:
    rows = []
    for case in case_scores:
        for concern in case.concern_scores:
            if not concern.known_gap and concern.outcome in {"false_positive", "miss"}:
                rows.append(
                    f"{case.case}/{concern.finding_ref}: {concern.outcome} "
                    f"expected={concern.expected_band} actual={concern.actual_severity}"
                )
        for finding_ref in case.unexpected_concerns:
            rows.append(f"{case.case}/{finding_ref}: false_positive unexpected concern")
    return rows
