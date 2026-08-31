"""Historical affinity scorer; recall affinity is inactive in current Engram."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

try:
    from integration_tests.eval.compare_backends import NOISE_THRESHOLD
    from integration_tests.eval.run_eval import run
except ModuleNotFoundError:  # Direct script execution.
    from compare_backends import NOISE_THRESHOLD
    from run_eval import run

DEFAULT_WEIGHTS = (0.05, 0.1, 0.15, 0.2, 0.3, 0.5)


def _parse_weights(raw: str) -> list[float]:
    weights = [float(value.strip()) for value in raw.split(",") if value.strip()]
    if not weights:
        raise ValueError("at least one affinity weight is required")
    return weights


def _trial(metrics: dict, label: str) -> dict:
    return next(
        (row for row in metrics["per_trial"] if row["label"] == label),
        {},
    )


def evaluate_candidate(
    baseline: dict,
    neural: dict,
    weight: float,
) -> dict:
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

    decoy_passed = decoy_delta > 0 or (decoy_delta == 0 and baseline_overall["recall_decoy"] >= 1.0)

    passed = (
        failures == 0
        and direct_delta >= -NOISE_THRESHOLD
        and paraphrase_delta >= -NOISE_THRESHOLD
        and decoy_passed  # Uses the updated fallback check
        and bleed_improvement > 0
    )
    return {
        "affinity_weight": weight,
        "recall_direct": neural_overall["recall_direct"],
        "recall_paraphrase": neural_overall["recall_paraphrase"],
        "recall_decoy": neural_overall["recall_decoy"],
        "contradiction_bleed_rate": neural_contradict["contradiction_bleed_rate"],
        "direct_delta": direct_delta,
        "paraphrase_delta": paraphrase_delta,
        "decoy_delta": decoy_delta,
        "contradiction_bleed_improvement": bleed_improvement,
        "failures": failures,
        "passed": passed,
    }


def render_table(rows: list[dict]) -> str:
    lines = [
        "# Neural Affinity Sweep",
        "",
        (
            "Pass requires improved decoy rejection and contradiction "
            "resistance, with direct and paraphrase recall no more than five "
            "percentage points below baseline."
        ),
        "",
        "| Weight | Direct | Paraphrase | Decoy | Contradiction Bleed | Pass |",
        "|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['affinity_weight']:.3f} | "
            f"{row['recall_direct']:.1%} | "
            f"{row['recall_paraphrase']:.1%} | "
            f"{row['recall_decoy']:.1%} | "
            f"{row['contradiction_bleed_rate']:.1%} | "
            f"{'yes' if row['passed'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def _run_args(
    *,
    backend: str,
    run_name: str,
    output_root: Path,
    trials: list[str],
    limit: int,
    model: str,
    ollama_url: str,
    embed_model: str,
    affinity_weight: float,
    judge_cache: Path,
    mode: str,
    answer_model: str | None,
    warmup_replays: int,
    neural_min_warmup_steps: int,
) -> Namespace:
    return Namespace(
        backend=backend,
        trials=trials,
        limit=limit,
        judge="ollama",
        model=model,
        ollama_url=ollama_url,
        embed_model=embed_model,
        output_root=str(output_root),
        run_name=run_name,
        affinity_weight=affinity_weight,
        surprise_threshold=0.001,
        neural_initialization_seed=42,
        neural_prompt_advisory=False,
        neural_importance_advisory=False,
        judge_cache=str(judge_cache),
        mode=mode,
        answer_model=answer_model,
        warmup_replays=warmup_replays,
        neural_min_warmup_steps=neural_min_warmup_steps,
        fresh=True,
        no_resume=False,
    )


async def run_sweep(args: argparse.Namespace) -> dict:
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    judge_cache = output_root / "judge_cache.json"
    weights = _parse_weights(args.affinity_weight_list)

    baseline = await run(
        _run_args(
            backend="baseline",
            run_name="baseline",
            output_root=output_root,
            trials=args.trials,
            limit=args.limit,
            model=args.model,
            ollama_url=args.ollama_url,
            embed_model=args.embed_model,
            affinity_weight=0.0,
            judge_cache=judge_cache,
            mode=args.mode,
            answer_model=args.answer_model,
            warmup_replays=args.warmup_replays,
            neural_min_warmup_steps=args.neural_min_warmup_steps,
        )
    )

    rows = []
    for weight in weights:
        run_name = f"neural_w{weight:g}".replace(".", "_")
        neural = await run(
            _run_args(
                backend="neural_on",
                run_name=run_name,
                output_root=output_root,
                trials=args.trials,
                limit=args.limit,
                model=args.model,
                ollama_url=args.ollama_url,
                embed_model=args.embed_model,
                affinity_weight=weight,
                judge_cache=judge_cache,
                mode=args.mode,
                answer_model=args.answer_model,
                warmup_replays=args.warmup_replays,
                neural_min_warmup_steps=args.neural_min_warmup_steps,
            )
        )
        rows.append(evaluate_candidate(baseline, neural, weight))

    report = {
        "model": args.model,
        "limit": args.limit,
        "trials": args.trials,
        "noise_threshold": NOISE_THRESHOLD,
        "weights": rows,
    }
    (output_root / "sweep.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    rendered = render_table(rows)
    (output_root / "sweep.md").write_text(rendered, encoding="utf-8")
    print(rendered)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--affinity-weight-list",
        default=",".join(str(value) for value in DEFAULT_WEIGHTS),
    )
    parser.add_argument(
        "--trials",
        nargs="+",
        default=["baseline", "contradict"],
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument(
        "--mode",
        choices=("retrieval", "generation"),
        default="retrieval",
    )
    parser.add_argument("--answer-model", default=None)
    parser.add_argument("--warmup-replays", type=int, default=1)
    parser.add_argument("--neural-min-warmup-steps", type=int, default=50)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--embed-model", default="nomic-embed-text")
    parser.add_argument(
        "--output-root",
        default=str(Path(__file__).resolve().parent / "runs" / "sweep"),
    )
    return parser.parse_args()


def main() -> None:
    raise SystemExit(
        "affinity_weight is inactive because the neural layer contributes no "
        "retrieval score. Use surprise_threshold_sweep.py to evaluate the "
        "active RTRL/TITANS write gate."
    )


if __name__ == "__main__":
    main()
