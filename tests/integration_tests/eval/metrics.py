"""Metrics for one current-architecture evaluation run."""

from __future__ import annotations

import json
import math
from pathlib import Path


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def compute_trial_metrics(trial: dict) -> dict:
    all_judgments = trial.get("judgment_results", [])
    judgments = [item for item in all_judgments if not item.get("judge_error")]
    metrics = {
        "trial_index": trial["trial_index"],
        "label": trial["label"],
        "subset": trial["subset_name"],
        "n_injections": len(trial.get("injection_results", [])),
        "n_judgments": len(judgments),
        "n_judge_failures": len(all_judgments) - len(judgments),
        "n_injection_failures": sum(
            not bool(item.get("success", False))
            for item in trial.get("injection_results", [])
        ),
        "n_neural_hints": sum(
            bool(item.get("neural_hint_present", False))
            for item in all_judgments
        ),
        "elapsed_sec": float(trial.get("elapsed_sec", 0.0)),
    }
    for query_type in ("direct", "paraphrase", "decoy"):
        subset = [
            item for item in judgments if item["query_type"] == query_type
        ]
        metrics[f"recall_{query_type}"] = (
            sum(bool(item["correct"]) for item in subset) / len(subset)
            if subset
            else None
        )
        metrics[f"relevance_{query_type}"] = _mean(
            [float(item["relevance"]) for item in subset]
        )

    non_decoy = [
        item for item in judgments if item["query_type"] != "decoy"
    ]
    metrics["contradiction_bleed_rate"] = (
        sum(bool(item["contaminated"]) for item in non_decoy) / len(non_decoy)
        if non_decoy
        else None
    )
    return metrics


def compute_metrics(
    trials: list[dict],
    backend: str,
    mode: str = "retrieval",
) -> dict:
    per_trial = [compute_trial_metrics(trial) for trial in trials]
    overall = {}
    for key in (
        "recall_direct",
        "recall_paraphrase",
        "recall_decoy",
        "contradiction_bleed_rate",
    ):
        values = [
            float(trial[key])
            for trial in per_trial
            if trial.get(key) is not None
            and not math.isnan(float(trial[key]))
        ]
        overall[key] = _mean(values)
    overall["judge_failures"] = sum(
        trial["n_judge_failures"] for trial in per_trial
    )
    overall["injection_failures"] = sum(
        trial["n_injection_failures"] for trial in per_trial
    )
    return {
        "backend": backend,
        "mode": mode,
        "per_trial": per_trial,
        "overall": overall,
    }


def save_metrics(
    trials: list[dict],
    backend: str,
    output_dir: str | Path,
    mode: str = "retrieval",
) -> dict:
    metrics = compute_metrics(trials, backend, mode=mode)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    return metrics
