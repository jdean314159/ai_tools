"""
rag_lib.eval.ragas_runner

RAGAS evaluation harness for rag_lib RAGPipeline.

D7: judge_llm is required — no default. Prevents self-evaluation bias.
D9: Run n_runs times, report median per metric to reduce LLM judge variance.

Supported judge configurations:
    # Claude Haiku (recommended — cheap, strong, avoids self-eval)
    from langchain_anthropic import ChatAnthropic
    from ragas.llms import LangchainLLMWrapper
    judge = LangchainLLMWrapper(ChatAnthropic(
        model="claude-haiku-4-5", temperature=0
    ))

    # Local Qwen (judging a smaller local generator)
    from langchain_community.chat_models import ChatOllama
    judge = LangchainLLMWrapper(ChatOllama(
        model="qwen3:32b", temperature=0
    ))

Usage:
    from rag_lib.eval.ragas_runner import run_eval, load_ground_truth

    queries = load_ground_truth("eval/ground_truth.jsonl")
    report = run_eval(pipeline, queries, judge_llm=judge, collection="default")
    print_report(report)
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import EvalError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MetricScores:
    """Per-metric scores across n_runs (median is the reported value)."""

    context_recall: float
    context_precision: float
    faithfulness: float
    answer_relevancy: float
    raw_runs: list[dict[str, float]] = field(default_factory=list)

    def passes(self, thresholds: dict[str, float]) -> bool:
        return (
            self.context_recall >= thresholds.get("context_recall", 0.85)
            and self.context_precision >= thresholds.get("context_precision", 0.80)
            and self.faithfulness >= thresholds.get("faithfulness", 0.88)
            and self.answer_relevancy >= thresholds.get("answer_relevancy", 0.80)
        )


@dataclass
class EvalReport:
    """Full evaluation report."""

    collection: str
    n_queries: int
    n_runs: int
    duration_seconds: float
    scores: MetricScores
    per_query_results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.scores.passes(self.thresholds)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_ground_truth(path: str | Path) -> list[dict[str, Any]]:
    """Load ground truth queries from a JSONL file.

    Each line must have:
        question (str)
        ground_truths (list[str])  — empty list for absent/negative queries
        difficulty (str)           — direct | inferential | multi_section |
                                     cross_document | absent

    Returns only queries with non-empty ground_truths (absent queries are
    excluded from context_recall measurement but included in faithfulness/
    answer_relevancy measurement separately).
    """
    path = Path(path)
    if not path.exists():
        raise EvalError(f"Ground truth file not found: {path}")

    queries: list[dict] = []
    absent: list[dict] = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                q = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvalError(f"Invalid JSON on line {i} of {path}: {exc}") from exc

            if q.get("difficulty") == "absent" or not q.get("ground_truths"):
                absent.append(q)
            else:
                queries.append(q)

    logger.info(
        "Loaded %d annotated queries + %d absent/negative queries from %s",
        len(queries),
        len(absent),
        path,
    )
    return queries


def load_all_queries(path: str | Path) -> tuple[list[dict], list[dict]]:
    """Load all queries, returning (annotated, absent) separately."""
    path = Path(path)
    annotated, absent = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            if q.get("difficulty") == "absent" or not q.get("ground_truths"):
                absent.append(q)
            else:
                annotated.append(q)
    return annotated, absent


def run_eval(
    pipeline: Any,
    test_queries: list[dict[str, Any]],
    *,
    judge_llm: Any,
    collection: str = "default",
    max_context_tokens: int | None = None,
    n_runs: int = 3,
    generate_answers: bool = True,
    generation_llm: Any = None,
    thresholds: dict[str, float] | None = None,
) -> EvalReport:
    """Run RAGAS evaluation on the pipeline.

    Args:
        pipeline:         RAGPipeline instance.
        test_queries:     List of dicts with 'question' and 'ground_truths'.
                          Use load_ground_truth() to load from JSONL.
        judge_llm:        Required. LangchainLLMWrapper around a judge model.
                          Must differ from the generation model to avoid self-eval.
        collection:       ChromaDB collection to retrieve from.
        max_context_tokens: Token budget for prompt assembly. Uses pipeline
                            config default if None.
        n_runs:           Number of evaluation runs; median is reported.
        generate_answers: If True, generates answers via generation_llm for
                          faithfulness and answer_relevancy metrics.
                          If False, only context_recall and context_precision
                          are measured.
        generation_llm:   LangchainLLMWrapper for answer generation. If None,
                          uses pipeline.generate() (returns "" by default —
                          set generate_answers=False or provide a generator).
        thresholds:       Pass/fail thresholds. Defaults from rag_lib.yaml.

    Returns:
        EvalReport with median scores across n_runs.

    Raises:
        EvalError: If judge_llm is None, RAGAS not installed, or evaluation fails.
    """
    if judge_llm is None:
        raise EvalError(
            "judge_llm is required. Using the same model as the generator measures "
            "self-consistency, not quality.\n"
            "Recommended: Claude Haiku (~$0.50/100 queries):\n"
            "  from langchain_anthropic import ChatAnthropic\n"
            "  from ragas.llms import LangchainLLMWrapper\n"
            "  judge = LangchainLLMWrapper(ChatAnthropic(model='claude-haiku-4-5', temperature=0))\n"
            "Acceptable: Qwen3:32b judging Qwen3:8b output:\n"
            "  from langchain_community.chat_models import ChatOllama\n"
            "  judge = LangchainLLMWrapper(ChatOllama(model='qwen3:32b', temperature=0))"
        )

    raise NotImplementedError(
        "RAGAS evaluation with an external judge is not implemented yet. "
        "This phase is reserved for the future evaluator integration."
    )

    if not test_queries:
        raise EvalError("test_queries is empty. Load ground truth with load_ground_truth().")

    try:
        from ragas import evaluate
        from ragas.metrics import (
            context_recall,
            context_precision,
            faithfulness,
            answer_relevancy,
        )
        from datasets import Dataset
    except ImportError as exc:
        raise EvalError(
            f"RAGAS not installed. Install with: pip install rag-lib[eval]\nMissing: {exc}"
        ) from exc

    _default_thresholds = {
        "context_recall": 0.85,
        "context_precision": 0.80,
        "faithfulness": 0.88,
        "answer_relevancy": 0.80,
    }
    effective_thresholds = {**_default_thresholds, **(thresholds or {})}

    t_start = time.perf_counter()
    run_results: list[dict[str, float]] = []
    per_query_results: list[dict] = []
    errors: list[str] = []

    # Select metrics based on whether answer generation is enabled
    metrics = [context_recall, context_precision]
    if generate_answers:
        metrics += [faithfulness, answer_relevancy]

    logger.info(
        "Starting RAGAS eval: %d queries, %d runs, collection='%s'",
        len(test_queries),
        n_runs,
        collection,
    )

    for run_num in range(1, n_runs + 1):
        logger.info("Run %d/%d...", run_num, n_runs)

        rows = []
        for q in test_queries:
            question = q["question"]
            ground_truths = q.get("ground_truths", [])

            try:
                # Retrieve contexts
                chunks = pipeline.retrieve(question, collection=collection)
                contexts = [c.content for c in chunks]

                # Assemble prompt and optionally generate answer
                answer = ""
                if generate_answers:
                    prompt = pipeline.assemble_prompt(
                        question,
                        chunks,
                        max_context_tokens=max_context_tokens,
                    )
                    if generation_llm is not None:
                        try:
                            resp = generation_llm.invoke(prompt)
                            answer = resp.content if hasattr(resp, "content") else str(resp)
                        except Exception as exc:
                            logger.warning(
                                "Generation failed for query '%s': %s", question[:60], exc
                            )
                            answer = ""
                    else:
                        answer = pipeline.generate(prompt)

                rows.append(
                    {
                        "question": question,
                        "answer": answer or "[no answer generated]",
                        "contexts": contexts,
                        "ground_truth": ground_truths[0] if ground_truths else "",
                        "ground_truths": ground_truths,
                    }
                )

            except Exception as exc:
                logger.warning("Query failed: '%s': %s", question[:60], exc)
                errors.append(f"Run {run_num}, query '{question[:60]}': {exc}")
                # Add a placeholder row so dataset size is consistent
                rows.append(
                    {
                        "question": question,
                        "answer": "",
                        "contexts": [],
                        "ground_truth": ground_truths[0] if ground_truths else "",
                        "ground_truths": ground_truths,
                    }
                )

        # Build RAGAS Dataset and evaluate
        try:
            dataset = Dataset.from_list(rows)
            result = evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=judge_llm,
                raise_exceptions=False,
            )

            run_scores = {
                "context_recall": float(result.get("context_recall", 0.0) or 0.0),
                "context_precision": float(result.get("context_precision", 0.0) or 0.0),
                "faithfulness": float(result.get("faithfulness", 0.0) or 0.0),
                "answer_relevancy": float(result.get("answer_relevancy", 0.0) or 0.0),
            }
            run_results.append(run_scores)
            logger.info("Run %d scores: %s", run_num, run_scores)

            # Capture per-query results on final run
            if run_num == n_runs and hasattr(result, "to_pandas"):
                try:
                    df = result.to_pandas()
                    per_query_results = df.to_dict("records")
                except Exception:
                    pass

        except Exception as exc:
            logger.error("RAGAS evaluation failed on run %d: %s", run_num, exc)
            errors.append(f"Run {run_num} evaluation failed: {exc}")

    # Compute median scores across runs
    def _median(key: str) -> float:
        vals = [r[key] for r in run_results if r.get(key) is not None]
        return round(statistics.median(vals), 4) if vals else 0.0

    scores = MetricScores(
        context_recall=_median("context_recall"),
        context_precision=_median("context_precision"),
        faithfulness=_median("faithfulness"),
        answer_relevancy=_median("answer_relevancy"),
        raw_runs=run_results,
    )

    duration = round(time.perf_counter() - t_start, 1)
    logger.info("Eval complete in %.1fs. Median scores: %s", duration, scores)

    return EvalReport(
        collection=collection,
        n_queries=len(test_queries),
        n_runs=n_runs,
        duration_seconds=duration,
        scores=scores,
        per_query_results=per_query_results,
        errors=errors,
        thresholds=effective_thresholds,
    )


def print_report(report: EvalReport) -> None:
    """Print a human-readable evaluation report."""
    width = 60
    print(f"\n{'=' * width}")
    print("  RAG EVALUATION REPORT")
    print(f"{'=' * width}")
    print(f"  Collection:   {report.collection}")
    print(f"  Queries:      {report.n_queries}")
    print(f"  Runs:         {report.n_runs} (median reported)")
    print(f"  Duration:     {report.duration_seconds:.1f}s")
    print(f"  Status:       {'PASSED ✓' if report.passed else 'FAILED ✗'}")
    print(f"\n  METRIC SCORES (median of {report.n_runs} runs)")
    print(f"  {'-' * 40}")

    metrics = [
        ("Context Recall", "context_recall", "retrieval quality"),
        ("Context Precision", "context_precision", "retrieval quality"),
        ("Faithfulness", "faithfulness", "generation quality"),
        ("Answer Relevancy", "answer_relevancy", "end-to-end quality"),
    ]

    for label, key, category in metrics:
        score = getattr(report.scores, key)
        threshold = report.thresholds.get(key, 0.0)
        status = "✓" if score >= threshold else "✗"
        print(f"  {status} {label:<22} {score:.4f}  (threshold {threshold:.2f}, {category})")

    if report.scores.raw_runs:
        print("\n  PER-RUN SCORES")
        print(f"  {'-' * 40}")
        for i, run in enumerate(report.scores.raw_runs, 1):
            cr = run.get("context_recall", 0)
            cp = run.get("context_precision", 0)
            fa = run.get("faithfulness", 0)
            ar = run.get("answer_relevancy", 0)
            print(
                f"  Run {i}: recall={cr:.3f}  precision={cp:.3f}  "
                f"faithful={fa:.3f}  relevancy={ar:.3f}"
            )

    if report.errors:
        print(f"\n  ERRORS ({len(report.errors)})")
        print(f"  {'-' * 40}")
        for err in report.errors[:5]:
            print(f"  • {err[:70]}")
        if len(report.errors) > 5:
            print(f"  ... and {len(report.errors) - 5} more")

    print(f"\n{'=' * width}\n")
