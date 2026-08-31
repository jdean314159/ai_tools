"""Calibrate and sweep the active RTRL/TITANS surprise write gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from argparse import Namespace
from pathlib import Path

try:
    from integration_tests.eval.compare_backends import NOISE_THRESHOLD
    from integration_tests.eval.run_eval import run
except ModuleNotFoundError:  # Direct script execution.
    from compare_backends import NOISE_THRESHOLD
    from run_eval import run


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("cannot compute a percentile from no surprise values")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def calibration_thresholds(
    values: list[float],
    percentiles: list[float],
    current_threshold: float,
) -> list[float]:
    candidates = [float(current_threshold)]
    candidates.extend(percentile(values, value / 100.0) for value in percentiles)
    return sorted({round(value, 8) for value in candidates})


def _trial(metrics: dict, label: str) -> dict:
    return next(
        (row for row in metrics["per_trial"] if row["label"] == label),
        {},
    )


def evaluate_candidate(baseline: dict, neural: dict, threshold: float) -> dict:
    baseline_overall = baseline["overall"]
    neural_overall = neural["overall"]
    baseline_contradict = _trial(baseline, "contradict")
    neural_contradict = _trial(neural, "contradict")
    direct_delta = neural_overall["recall_direct"] - baseline_overall["recall_direct"]
    paraphrase_delta = neural_overall["recall_paraphrase"] - baseline_overall["recall_paraphrase"]
    decoy_delta = neural_overall["recall_decoy"] - baseline_overall["recall_decoy"]
    bleed_improvement = (
        baseline_contradict["contradiction_bleed_rate"]
        - neural_contradict["contradiction_bleed_rate"]
    )
    failures = int(neural_overall.get("judge_failures", 0)) + int(
        neural_overall.get("injection_failures", 0)
    )
    observations = sum(int(row.get("n_neural_observations", 0)) for row in neural["per_trial"])
    writes = sum(int(row.get("n_neural_writes", 0)) for row in neural["per_trial"])
    return {
        "surprise_threshold": threshold,
        "recall_direct": neural_overall["recall_direct"],
        "recall_paraphrase": neural_overall["recall_paraphrase"],
        "recall_decoy": neural_overall["recall_decoy"],
        "contradiction_bleed_rate": neural_contradict["contradiction_bleed_rate"],
        "direct_delta": direct_delta,
        "paraphrase_delta": paraphrase_delta,
        "decoy_delta": decoy_delta,
        "contradiction_bleed_improvement": bleed_improvement,
        "neural_observations": observations,
        "neural_writes": writes,
        "neural_write_ratio": writes / observations if observations else None,
        "failures": failures,
        "passed": (
            failures == 0
            and direct_delta >= -NOISE_THRESHOLD
            and paraphrase_delta >= -NOISE_THRESHOLD
            and (decoy_delta > 0 or (decoy_delta == 0 and baseline_overall["recall_decoy"] >= 1.0))
            and bleed_improvement > 0
        ),
    }


def _run_args(
    args: argparse.Namespace, *, backend: str, run_name: str, threshold: float
) -> Namespace:
    return Namespace(
        backend=backend,
        trials=args.trials,
        limit=args.limit,
        judge="ollama",
        model=args.model,
        mode=args.mode,
        answer_model=args.answer_model,
        warmup_replays=args.warmup_replays,
        neural_min_warmup_steps=args.neural_min_warmup_steps,
        ollama_url=args.ollama_url,
        embed_model=args.embed_model,
        output_root=args.output_root,
        run_name=run_name,
        affinity_weight=0.15,
        surprise_threshold=threshold,
        neural_initialization_seed=args.neural_initialization_seed,
        neural_prompt_advisory=True,
        neural_importance_advisory=True,
        judge_cache=str(Path(args.output_root) / "judge_cache.json"),
        fresh=True,
        no_resume=False,
    )


def _surprises(path: Path) -> list[float]:
    trials = json.loads(path.read_text(encoding="utf-8"))
    return [
        float(item["novelty_score"])
        for trial in trials
        for item in trial.get("injection_results", [])
        if item.get("novelty_score") is not None
    ]


def render_table(rows: list[dict]) -> str:
    lines = [
        "# Neural Surprise-Threshold Sweep",
        "",
        "| Threshold | Write ratio | Direct | Paraphrase | Decoy | Contradiction bleed | Pass |",
        "|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in rows:
        ratio = row["neural_write_ratio"]
        lines.append(
            f"| {row['surprise_threshold']:.6g} | "
            f"{ratio:.1%} | {row['recall_direct']:.1%} | "
            f"{row['recall_paraphrase']:.1%} | {row['recall_decoy']:.1%} | "
            f"{row['contradiction_bleed_rate']:.1%} | "
            f"{'yes' if row['passed'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


async def run_sweep(args: argparse.Namespace) -> dict:
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    baseline = await run(_run_args(args, backend="baseline", run_name="baseline", threshold=0.0))
    await run(_run_args(args, backend="neural_on", run_name="calibration", threshold=0.0))
    values = _surprises(output_root / "calibration" / "results" / "all_trials.json")
    thresholds = calibration_thresholds(
        values,
        [float(value) for value in args.percentiles.split(",") if value.strip()],
        args.current_threshold,
    )
    rows = []
    for threshold in thresholds:
        neural = await run(
            _run_args(
                args,
                backend="neural_on",
                run_name=f"threshold_{threshold:.8g}".replace(".", "_"),
                threshold=threshold,
            )
        )
        rows.append(evaluate_candidate(baseline, neural, threshold))
    report = {
        "model": args.model,
        "mode": args.mode,
        "limit": args.limit,
        "trials": args.trials,
        "calibration": {
            "count": len(values),
            "minimum": min(values),
            "maximum": max(values),
            "mean": sum(values) / len(values),
            "percentiles": {
                value: percentile(values, float(value) / 100.0)
                for value in args.percentiles.split(",")
                if value.strip()
            },
        },
        "thresholds": rows,
    }
    (output_root / "sweep.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    rendered = render_table(rows)
    (output_root / "sweep.md").write_text(rendered, encoding="utf-8")
    print(rendered)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", nargs="+", default=["baseline", "contradict"])
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--mode", choices=("retrieval", "generation"), default="generation")
    parser.add_argument("--answer-model", default=None)
    parser.add_argument("--warmup-replays", type=int, default=1)
    parser.add_argument("--neural-min-warmup-steps", type=int, default=50)
    parser.add_argument("--neural-initialization-seed", type=int, default=42)
    parser.add_argument("--current-threshold", type=float, default=0.001)
    parser.add_argument("--percentiles", default="25,50,75")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--embed-model", default="nomic-embed-text")
    parser.add_argument(
        "--output-root",
        default=str(Path(__file__).resolve().parent / "runs" / "surprise-sweep"),
    )
    return parser.parse_args()


def main() -> None:
    asyncio.run(run_sweep(parse_args()))


if __name__ == "__main__":
    main()
