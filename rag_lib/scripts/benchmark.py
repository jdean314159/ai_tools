#!/usr/bin/env python3
"""
scripts/benchmark.py

Run the RAGAS benchmark against a fully ingested rag_lib collection.

Usage:
    cd ~/ai_tools
    python rag_lib/scripts/benchmark.py \
        --judge claude-haiku \
        --ground-truth rag_lib/eval/ground_truth.jsonl \
        --collection default \
        [--generator qwen3:8b] \
        [--n-runs 3] \
        [--config rag_lib/data/rag_lib.yaml]

Judge model options:
    claude-haiku      Claude Haiku via Anthropic API (requires ANTHROPIC_API_KEY)
    claude-sonnet     Claude Sonnet (more expensive, stronger judge)
    qwen3:32b         Local Qwen3 32B via Ollama (slower, no API cost)
    qwen3:8b          Local Qwen3 8B (faster but weaker judge)

The judge model should be DIFFERENT from and STRONGER than the generator.
Self-evaluation (same model generating and judging) measures self-consistency,
not quality.

Exit codes:
    0   All metrics passed thresholds
    1   One or more metrics failed thresholds
    2   Evaluation error (RAGAS, network, or config failure)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add rag_lib to path
SCRIPT_DIR = Path(__file__).resolve().parent
RAG_LIB_SRC = SCRIPT_DIR.parent / "src"
LLM_ENGINES_SRC = SCRIPT_DIR.parent.parent / "llm_engines"
sys.path.insert(0, str(RAG_LIB_SRC))
if LLM_ENGINES_SRC.exists():
    sys.path.insert(0, str(LLM_ENGINES_SRC))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("benchmark")


def make_judge(judge_spec: str) -> Any:
    """Build a LangchainLLMWrapper judge from a spec string."""
    try:
        from ragas.llms import LangchainLLMWrapper
    except ImportError:
        print("ERROR: ragas not installed. Run: pip install rag-lib[eval]")
        sys.exit(2)

    # Claude models
    if "claude" in judge_spec.lower() or "haiku" in judge_spec.lower() or "sonnet" in judge_spec.lower():
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not set. Export it before running.")
            sys.exit(2)
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            print("ERROR: langchain-anthropic not installed. Run: pip install langchain-anthropic")
            sys.exit(2)

        model_map = {
            "claude-haiku": "claude-haiku-4-5",
            "claude-sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5",
            "sonnet": "claude-sonnet-4-6",
        }
        model_name = model_map.get(judge_spec.lower(), judge_spec)
        logger.info("Using Claude judge: %s", model_name)
        return LangchainLLMWrapper(ChatAnthropic(model=model_name, temperature=0))

    # Ollama local models
    else:
        try:
            from langchain_community.chat_models import ChatOllama
        except ImportError:
            print("ERROR: langchain-community not installed. Run: pip install langchain-community")
            sys.exit(2)
        logger.info("Using local Ollama judge: %s", judge_spec)
        return LangchainLLMWrapper(ChatOllama(model=judge_spec, temperature=0))


def make_generator(generator_spec: str | None) -> Any:
    """Build a generation LLM from a spec string. Returns None if not specified."""
    if not generator_spec:
        return None

    if "claude" in generator_spec.lower():
        try:
            from langchain_anthropic import ChatAnthropic
            from ragas.llms import LangchainLLMWrapper
            return LangchainLLMWrapper(ChatAnthropic(
                model=generator_spec, temperature=0.1
            ))
        except ImportError:
            logger.warning("langchain-anthropic not installed; skipping answer generation")
            return None
    else:
        try:
            from langchain_community.chat_models import ChatOllama
            from ragas.llms import LangchainLLMWrapper
            logger.info("Using local Ollama generator: %s", generator_spec)
            return LangchainLLMWrapper(ChatOllama(model=generator_spec, temperature=0.1))
        except ImportError:
            logger.warning("langchain-community not installed; skipping answer generation")
            return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run RAGAS benchmark on a rag_lib collection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--judge", required=True,
        help="Judge model: claude-haiku | claude-sonnet | qwen3:32b | qwen3:8b"
    )
    parser.add_argument(
        "--ground-truth", default="eval/ground_truth.jsonl",
        help="Path to ground truth JSONL file (default: eval/ground_truth.jsonl)"
    )
    parser.add_argument(
        "--collection", default="default",
        help="ChromaDB collection name (default: default)"
    )
    parser.add_argument(
        "--generator", default=None,
        help="Generation model for faithfulness/relevancy (e.g. qwen3:8b). "
             "If not set, only context_recall and context_precision are measured."
    )
    parser.add_argument(
        "--n-runs", type=int, default=3,
        help="Number of evaluation runs; median is reported (default: 3)"
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to rag_lib.yaml config file"
    )
    parser.add_argument(
        "--max-context-tokens", type=int, default=None,
        help="Token budget for prompt assembly (uses config default if not set)"
    )
    parser.add_argument(
        "--output", default=None,
        help="Write JSON report to this file path"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Import rag_lib
    try:
        from rag_lib import RAGPipeline
        from rag_lib.eval.ragas_runner import (
            run_eval, load_ground_truth, print_report
        )
    except ImportError as exc:
        print(f"ERROR: Cannot import rag_lib: {exc}")
        print("Ensure you're running from ~/ai_tools/ with rag_lib installed.")
        return 2

    # Load ground truth
    gt_path = Path(args.ground_truth)
    if not gt_path.is_absolute():
        # Try relative to script dir parent (rag_lib root)
        candidates = [
            gt_path,
            SCRIPT_DIR.parent / gt_path,
            Path.cwd() / gt_path,
        ]
        gt_path = next((p for p in candidates if p.exists()), gt_path)

    try:
        queries = load_ground_truth(gt_path)
    except Exception as exc:
        print(f"ERROR loading ground truth from {gt_path}: {exc}")
        return 2

    print(f"\nBenchmark configuration:")
    print(f"  Judge:        {args.judge}")
    print(f"  Generator:    {args.generator or '(none — retrieval metrics only)'}")
    print(f"  Collection:   {args.collection}")
    print(f"  Queries:      {len(queries)}")
    print(f"  Runs:         {args.n_runs}")
    print()

    # Build pipeline
    try:
        pipeline = RAGPipeline(config=args.config)
    except Exception as exc:
        print(f"ERROR initializing RAGPipeline: {exc}")
        return 2

    # Build judge and generator
    try:
        judge = make_judge(args.judge)
        generator = make_generator(args.generator)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR building judge/generator: {exc}")
        return 2

    # Run evaluation
    try:
        report = run_eval(
            pipeline=pipeline,
            test_queries=queries,
            judge_llm=judge,
            collection=args.collection,
            max_context_tokens=args.max_context_tokens,
            n_runs=args.n_runs,
            generate_answers=generator is not None,
            generation_llm=generator,
        )
    except Exception as exc:
        print(f"ERROR during evaluation: {exc}")
        logger.exception("Evaluation failed")
        return 2

    # Print report
    print_report(report)

    # Write JSON output if requested
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report_dict = {
            "collection": report.collection,
            "n_queries": report.n_queries,
            "n_runs": report.n_runs,
            "duration_seconds": report.duration_seconds,
            "passed": report.passed,
            "scores": {
                "context_recall": report.scores.context_recall,
                "context_precision": report.scores.context_precision,
                "faithfulness": report.scores.faithfulness,
                "answer_relevancy": report.scores.answer_relevancy,
            },
            "thresholds": report.thresholds,
            "raw_runs": report.scores.raw_runs,
            "errors": report.errors,
        }
        out_path.write_text(json.dumps(report_dict, indent=2))
        print(f"Report written to: {out_path}")

    return 0 if report.passed else 1


# Type hint for make_judge/make_generator return
from typing import Any  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
