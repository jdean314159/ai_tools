"""Compare fresh neural-on metrics against a fresh baseline."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

METRICS = (
    ("recall_direct", "higher"),
    ("recall_paraphrase", "higher"),
    ("recall_decoy", "higher"),
    ("contradiction_bleed_rate", "lower"),
)
TRIAL_LABELS = (
    "baseline",
    "reinforce_3x",
    "reinforce_8x",
    "contradict",
    "forgetting",
    "cold_query",
)

# Declared before the run: changes within five percentage points are noise.
NOISE_THRESHOLD = 0.05


def _load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _index(metrics: dict) -> dict[str, dict]:
    return {row["label"]: row for row in metrics["per_trial"]}


def _delta(baseline: float | None, neural: float | None, direction: str):
    if baseline is None or neural is None:
        return None
    raw = neural - baseline
    return raw if direction == "higher" else -raw


def compare_metrics(baseline: dict, neural: dict) -> dict:
    baseline_mode = str(baseline.get("mode", "retrieval"))
    neural_mode = str(neural.get("mode", "retrieval"))
    if baseline_mode != neural_mode:
        raise ValueError(
            "Cannot compare evaluation runs with different modes: "
            f"{baseline_mode!r} != {neural_mode!r}"
        )
    baseline_trials = _index(baseline)
    neural_trials = _index(neural)
    rows = []
    regressions = []
    for metric, direction in METRICS:
        for label in TRIAL_LABELS:
            baseline_value = baseline_trials.get(label, {}).get(metric)
            neural_value = neural_trials.get(label, {}).get(metric)
            improvement = _delta(baseline_value, neural_value, direction)
            status = "unavailable"
            if improvement is not None:
                if improvement > NOISE_THRESHOLD:
                    status = "improved"
                elif improvement < -NOISE_THRESHOLD:
                    status = "regressed"
                    regressions.append(
                        {"metric": metric, "trial": label, "delta": improvement}
                    )
                else:
                    status = "within_noise"
            rows.append(
                {
                    "metric": metric,
                    "trial": label,
                    "direction": direction,
                    "baseline": baseline_value,
                    "neural_on": neural_value,
                    "raw_delta": (
                        neural_value - baseline_value
                        if baseline_value is not None and neural_value is not None
                        else None
                    ),
                    "improvement_delta": improvement,
                    "status": status,
                }
            )

    baseline_overall = baseline.get("overall", {})
    neural_overall = neural.get("overall", {})
    overall = {}
    for metric, direction in METRICS:
        baseline_value = baseline_overall.get(metric)
        neural_value = neural_overall.get(metric)
        overall[metric] = {
            "baseline": baseline_value,
            "neural_on": neural_value,
            "improvement_delta": _delta(
                baseline_value,
                neural_value,
                direction,
            ),
        }

    decoy_delta = overall["recall_decoy"]["improvement_delta"]
    contradict_row = next(
        row
        for row in rows
        if row["metric"] == "contradiction_bleed_rate"
        and row["trial"] == "contradict"
    )
    contradiction_delta = contradict_row["improvement_delta"]
    direct_delta = overall["recall_direct"]["improvement_delta"]
    paraphrase_delta = overall["recall_paraphrase"]["improvement_delta"]

    criteria = {
        "noise_threshold": NOISE_THRESHOLD,
        "complete_evaluation": (
            set(baseline_trials) == set(TRIAL_LABELS)
            and set(neural_trials) == set(TRIAL_LABELS)
            and int(baseline_overall.get("judge_failures", 0)) == 0
            and int(neural_overall.get("judge_failures", 0)) == 0
            and int(baseline_overall.get("injection_failures", 0)) == 0
            and int(neural_overall.get("injection_failures", 0)) == 0
        ),
        "decoy_rejection_improves": decoy_delta is not None and decoy_delta > 0,
        "contradiction_resistance_improves": (
            contradiction_delta is not None and contradiction_delta > 0
        ),
        "direct_recall_no_material_drop": (
            direct_delta is not None and direct_delta >= -NOISE_THRESHOLD
        ),
        "paraphrase_recall_no_material_drop": (
            paraphrase_delta is not None
            and paraphrase_delta >= -NOISE_THRESHOLD
        ),
        "no_metric_regresses_beyond_noise": not regressions,
    }
    verdict = (
        "eligible_for_default_on"
        if all(criteria[key] for key in criteria if key != "noise_threshold")
        else "remain_default_off"
    )
    return {
        "mode": baseline_mode,
        "decision_rule": (
            "Neural must improve decoy rejection and contradict-trial "
            "resistance, avoid material direct/paraphrase recall loss, and "
            "have no metric regress beyond the five-point noise threshold."
        ),
        "criteria": criteria,
        "verdict": verdict,
        "overall": overall,
        "per_trial": rows,
        "regressions": regressions,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Neural Memory A/B Comparison",
        "",
        f"Verdict: **{report['verdict']}**",
        "",
        report["decision_rule"],
        "",
        "## Overall",
        "",
        "| Metric | Baseline | Neural | Improvement |",
        "|---|---:|---:|---:|",
    ]
    for metric, values in report["overall"].items():
        def overall_fmt(value):
            return "n/a" if value is None else f"{value:.1%}"

        lines.append(
            f"| {metric} | {overall_fmt(values['baseline'])} | "
            f"{overall_fmt(values['neural_on'])} | "
            f"{overall_fmt(values['improvement_delta'])} |"
        )
    lines.extend(
        [
            "",
            "## Per Trial",
            "",
        "| Metric | Trial | Baseline | Neural | Delta | Status |",
        "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in report["per_trial"]:
        def fmt(value):
            return "n/a" if value is None else f"{value:.1%}"

        raw_delta = row["raw_delta"]
        lines.append(
            f"| {row['metric']} | {row['trial']} | "
            f"{fmt(row['baseline'])} | {fmt(row['neural_on'])} | "
            f"{fmt(raw_delta)} | {row['status']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--neural-on", required=True, dest="neural_on")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = compare_metrics(_load(args.baseline), _load(args.neural_on))
    rendered = render_markdown(report)
    print(rendered)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        path.with_suffix(".json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
