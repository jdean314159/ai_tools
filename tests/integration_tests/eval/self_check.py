"""Offline structural checks for the explicitly-run evaluation harness."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from .compare_backends import compare_metrics
from .corpus import Fact, FactCorpus
from .engram_probe import RetrievalResult
from .eval_config import EvalConfig
from .metrics import compute_metrics
from .ollama_judge import OllamaJudge
from .sweep import evaluate_candidate


async def _judge_cache_check() -> None:
    fact = Fact(
        id="fact",
        category="test",
        salience="high",
        canonical="The answer is blue.",
        contradiction="The answer is red.",
        direct_query="What is the answer?",
        paraphrase_query="Which color is correct?",
        decoy_query="What is another answer?",
        expected_snippet="answer is blue",
    )
    retrieval = RetrievalResult(
        fact_id=fact.id,
        query=fact.direct_query,
        query_type="direct",
        top_k=1,
        retrieved_chunks=[fact.canonical],
        elapsed_ms=1.0,
        success=True,
    )
    raw = (
        '{"retrieved":true,"relevance":5,"contaminated":false,'
        '"verbatim_match":true,"notes":"exact"}'
    )

    with tempfile.TemporaryDirectory() as directory:
        cache_path = Path(directory) / "judge_cache.json"
        calls = {"count": 0}

        async def fake_call(prompt: str):
            del prompt
            calls["count"] += 1
            return raw, None

        cached = OllamaJudge(concurrency=4, cache_path=cache_path)
        cached._call_ollama = fake_call
        first = await cached.judge(fact, retrieval, 0)
        second = await cached.judge(fact, retrieval, 1)

        uncached = OllamaJudge(concurrency=1)
        uncached._call_ollama = fake_call
        third = await uncached.judge(fact, retrieval, 2)

        assert calls["count"] == 2
        assert first.as_dict() | {"trial": 0} == second.as_dict() | {"trial": 0}
        assert first.as_dict() | {"trial": 0} == third.as_dict() | {"trial": 0}
        assert cache_path.exists()


def main() -> None:
    config = EvalConfig()
    corpus = FactCorpus.load(config.corpus_path)
    assert len(corpus) == 60
    assert config.backends == ("baseline", "neural_on")
    assert [row[0] for row in config.schedule] == [
        "baseline",
        "reinforce_3x",
        "reinforce_8x",
        "contradict",
        "forgetting",
        "cold_query",
    ]
    assert (
        OllamaJudge._extract_json('<think>hidden</think>```json\n{"retrieved": true}\n```')
        == '{"retrieved": true}'
    )

    trial = {
        "trial_index": 0,
        "label": "baseline",
        "subset_name": "all",
        "injection_results": [],
        "elapsed_sec": 1.0,
        "judgment_results": [
            {
                "query_type": "direct",
                "correct": True,
                "relevance": 5,
                "contaminated": False,
                "judge_error": None,
            },
            {
                "query_type": "decoy",
                "correct": True,
                "relevance": 0,
                "contaminated": False,
                "judge_error": None,
            },
            {
                "query_type": "paraphrase",
                "correct": False,
                "relevance": 0,
                "contaminated": False,
                "judge_error": "timeout",
            },
        ],
    }
    baseline = compute_metrics([trial], "baseline")
    neural = compute_metrics([trial], "neural_on")
    assert baseline["per_trial"][0]["n_judge_failures"] == 1
    report = compare_metrics(baseline, neural)
    assert report["verdict"] == "remain_default_off"
    assert report["criteria"]["complete_evaluation"] is False

    def complete_metrics(backend: str, *, neural_on: bool) -> dict:
        return {
            "backend": backend,
            "per_trial": [
                {
                    "label": label,
                    "recall_direct": 0.8,
                    "recall_paraphrase": 0.8,
                    "recall_decoy": 0.7 if neural_on else 0.6,
                    "contradiction_bleed_rate": (0.1 if neural_on else 0.2),
                }
                for label in (
                    "baseline",
                    "reinforce_3x",
                    "reinforce_8x",
                    "contradict",
                    "forgetting",
                    "cold_query",
                )
            ],
            "overall": {
                "recall_direct": 0.8,
                "recall_paraphrase": 0.8,
                "recall_decoy": 0.7 if neural_on else 0.6,
                "contradiction_bleed_rate": 0.1 if neural_on else 0.2,
                "judge_failures": 0,
                "injection_failures": 0,
            },
        }

    eligible = compare_metrics(
        complete_metrics("baseline", neural_on=False),
        complete_metrics("neural_on", neural_on=True),
    )
    assert eligible["verdict"] == "eligible_for_default_on"

    sweep_row = evaluate_candidate(
        complete_metrics("baseline", neural_on=False),
        complete_metrics("neural_on", neural_on=True),
        0.15,
    )
    assert sweep_row["passed"] is True
    asyncio.run(_judge_cache_check())
    print("eval harness self-check passed")


if __name__ == "__main__":
    main()
