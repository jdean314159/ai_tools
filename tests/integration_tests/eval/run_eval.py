"""Run one side of the current Engram neural memory A/B."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from pathlib import Path

try:
    from integration_tests.eval.corpus import FactCorpus
    from integration_tests.eval.engram_probe import EngramProbe
    from integration_tests.eval.eval_config import EvalConfig
    from integration_tests.eval.metrics import save_metrics
    from integration_tests.eval.ollama_judge import OllamaJudge
    from integration_tests.eval.trial_runner import TrialRunner
except ModuleNotFoundError:  # Direct script execution from the repository root.
    from corpus import FactCorpus
    from engram_probe import EngramProbe
    from eval_config import EvalConfig
    from metrics import save_metrics
    from ollama_judge import OllamaJudge
    from trial_runner import TrialRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run baseline or neural-on Engram memory evaluation"
    )
    parser.add_argument(
        "--backend",
        required=True,
        choices=("baseline", "neural_on"),
    )
    parser.add_argument(
        "--trials",
        nargs="+",
        default=None,
        help="Trial labels, space- or comma-separated; default is all six",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--judge", choices=("ollama",), default="ollama")
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
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--affinity-weight", type=float, default=0.15)
    parser.add_argument("--surprise-threshold", type=float, default=0.001)
    parser.add_argument("--neural-initialization-seed", type=int, default=42)
    parser.add_argument("--neural-prompt-advisory", action="store_true")
    parser.add_argument("--neural-importance-advisory", action="store_true")
    parser.add_argument("--judge-cache", default=None)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete this backend's prior run and memory state first",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Rerun selected trials even when result files exist",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict:
    config = EvalConfig(
        judge_model=args.model,
        judge_base_url=args.ollama_url,
        embed_model=args.embed_model,
        embed_base_url=args.ollama_url,
        affinity_weight=args.affinity_weight,
        surprise_threshold=args.surprise_threshold,
        neural_initialization_seed=args.neural_initialization_seed,
        neural_prompt_advisory_enabled=args.neural_prompt_advisory,
        neural_importance_advisory_enabled=args.neural_importance_advisory,
        mode=args.mode,
        answer_model=args.answer_model or args.model,
        warmup_replays=args.warmup_replays,
        neural_min_warmup_steps=args.neural_min_warmup_steps,
    )
    if args.output_root:
        config.output_root = Path(args.output_root)
    config.validate_backend(args.backend)
    config.validate_mode()

    if args.trials:
        labels = {
            label.strip() for value in args.trials for label in value.split(",") if label.strip()
        }
        unknown = labels - {entry[0] for entry in config.schedule}
        if unknown:
            raise ValueError(f"Unknown trial labels: {sorted(unknown)}")
        config.schedule = [entry for entry in config.schedule if entry[0] in labels]

    backend_root = config.output_root / (args.run_name or args.backend)
    output_dir = backend_root / "results"
    storage_dir = backend_root / "memory"
    if args.fresh and backend_root.exists():
        shutil.rmtree(backend_root)

    corpus = FactCorpus.load(config.corpus_path).limited(args.limit)
    probe = EngramProbe(config, args.backend, storage_dir)
    judge = OllamaJudge(
        model=config.judge_model,
        base_url=config.judge_base_url,
        max_tokens=config.judge_max_tokens,
        timeout_sec=config.judge_timeout_sec,
        retries=config.judge_retries,
        concurrency=config.judge_concurrency,
        cache_path=args.judge_cache or (backend_root / "judge_cache.json"),
    )
    await probe.start()
    await judge.start()
    try:
        runner = TrialRunner(config, corpus, probe, judge, output_dir)
        records = await runner.run_all(resume=not args.no_resume)
        metrics = save_metrics(
            [record.__dict__ for record in records],
            args.backend,
            output_dir,
            mode=config.mode,
        )
        print(json.dumps(metrics, indent=2))
        return metrics
    finally:
        await judge.stop()
        await probe.stop()


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
