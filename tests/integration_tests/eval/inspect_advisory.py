"""Inspect neural prompt-advisory episode alignment without generation."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from engram import ProjectMemory, ProjectType, RecallQuery
from engram.embeddings.ollama import OllamaEmbedder
from engram.neural import NeuralMemoryConfig

try:
    from integration_tests.eval.corpus import FactCorpus
except ModuleNotFoundError:
    from corpus import FactCorpus


def inspect(args: argparse.Namespace) -> dict:
    embedder = OllamaEmbedder(
        model=args.embed_model,
        base_url=args.ollama_url,
        timeout=120,
    )
    memory = ProjectMemory(
        base_dir=Path(args.memory_root),
        project_id="neural_ab_eval",
        project_type=ProjectType.GENERAL_ASSISTANT,
        session_id="eval_session_0",
        embedder=embedder,
        enable_neural=True,
        neural_config=NeuralMemoryConfig(
            surprise_threshold=args.surprise_threshold,
            initialization_seed=args.neural_initialization_seed,
            prompt_advisory_enabled=True,
        ),
        auto_pair_assistant=False,
        enable_semantic_graph=True,
    )
    corpus = FactCorpus.load(args.corpus)
    rows = []
    try:
        if memory.neural_layer is None:
            raise RuntimeError("saved neural layer did not load")
        for fact in corpus.facts:
            expect_contradiction = fact.salience == "high"
            expected = fact.contradiction if expect_contradiction else fact.canonical
            stale = fact.canonical if expect_contradiction else fact.contradiction
            for query_type, query in (
                ("direct", fact.direct_query),
                ("paraphrase", fact.paraphrase_query),
                ("decoy", fact.decoy_query),
            ):
                retrieval_texts = {str(item.text) for item in memory.search_episodes(query, n=3)}
                hint = memory.neural_layer.contribute_to_prompt(
                    RecallQuery(query=query, session_id=memory.session_id)
                )
                episodes = (
                    list(hint.metadata.get("aligned_episodes", [])) if hint is not None else []
                )
                texts = {str(item.get("text", "")) for item in episodes}
                rows.append(
                    {
                        "fact_id": fact.id,
                        "query_type": query_type,
                        "query": query,
                        "expected_present": expected in texts,
                        "stale_present": stale in texts,
                        "retrieval_expected_present": expected in retrieval_texts,
                        "retrieval_stale_present": stale in retrieval_texts,
                        "hint_text": hint.text if hint is not None else None,
                        "episodes": episodes,
                    }
                )
    finally:
        memory.close()

    by_type: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        bucket = by_type[row["query_type"]]
        bucket["queries"] += 1
        bucket["expected"] += int(row["expected_present"])
        bucket["stale"] += int(row["stale_present"])
        bucket["retrieval_expected"] += int(row["retrieval_expected_present"])
        bucket["retrieval_stale"] += int(row["retrieval_stale_present"])
        bucket["neither"] += int(not row["expected_present"] and not row["stale_present"])
    summary = {
        query_type: {key: int(value) for key, value in counts.items()}
        for query_type, counts in by_type.items()
    }
    report = {"summary": summary, "rows": rows}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--corpus",
        default=str(Path(__file__).resolve().parent / "eval_corpus.json"),
    )
    parser.add_argument("--surprise-threshold", type=float, default=0.001)
    parser.add_argument("--neural-initialization-seed", type=int, default=42)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--embed-model", default="nomic-embed-text")
    return parser.parse_args()


if __name__ == "__main__":
    inspect(parse_args())
