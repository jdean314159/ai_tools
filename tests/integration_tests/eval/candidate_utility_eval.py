"""Held-out experiment for RTRL candidate-utility scoring."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from engram.embeddings.ollama import OllamaEmbedder
from engram.neural.core import ModernSubgroupedRTRL, RTRLConfig

try:
    from integration_tests.eval.corpus import FactCorpus
except ModuleNotFoundError:
    from corpus import FactCorpus


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator > 1e-12 else 0.0


def _features(
    query: str,
    candidate: dict,
    *,
    similarity: float,
    rank: int,
    score_spread: float,
) -> np.ndarray:
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(candidate["text"])
    union = query_tokens | candidate_tokens
    jaccard = len(query_tokens & candidate_tokens) / len(union) if union else 0.0
    length_ratio = min(len(query_tokens), len(candidate_tokens)) / max(
        1, max(len(query_tokens), len(candidate_tokens))
    )
    return np.asarray(
        [
            similarity,
            1.0 / max(1, rank),
            score_spread,
            jaccard,
            float(candidate["importance"]),
            float(candidate["recency"]),
            float(candidate["repetition"]),
            length_ratio,
        ],
        dtype=np.float32,
    )


def _embed_texts(
    texts: list[str],
    *,
    cache_path: Path,
    model: str,
    base_url: str,
) -> dict[str, np.ndarray]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    embedder = OllamaEmbedder(model=model, base_url=base_url, timeout=120)
    missing = [text for text in texts if text not in cached]
    for index, text in enumerate(missing, start=1):
        cached[text] = embedder.embed(text).embedding
        if index % 25 == 0:
            cache_path.write_text(json.dumps(cached), encoding="utf-8")
    cache_path.write_text(json.dumps(cached), encoding="utf-8")
    return {text: np.asarray(cached[text], dtype=np.float32) for text in texts}


def build_dataset(corpus: FactCorpus, embeddings: dict[str, np.ndarray]) -> list[dict]:
    candidates = []
    for fact in corpus.facts:
        candidates.extend(
            [
                {
                    "id": f"{fact.id}:canonical",
                    "fact_id": fact.id,
                    "kind": "canonical",
                    "text": fact.canonical,
                    "importance": 0.6,
                    "recency": 0.4,
                    "repetition": 0.125 if fact.salience == "high" else 0.0,
                },
                {
                    "id": f"{fact.id}:contradiction",
                    "fact_id": fact.id,
                    "kind": "contradiction",
                    "text": fact.contradiction,
                    "importance": 0.6,
                    "recency": 0.7,
                    "repetition": 0.0,
                },
            ]
        )
    for index in range(200):
        candidates.append(
            {
                "id": f"distractor:{index}",
                "fact_id": None,
                "kind": "distractor",
                "text": (
                    f"Distractor {index}: The quarterly budget review showed a "
                    f"3.2% variance in line item {index % 50 + 1}. The audit "
                    "committee noted this for follow-up."
                ),
                "importance": 0.3,
                "recency": 1.0,
                "repetition": 0.0,
            }
        )

    rows = []
    for fact in corpus.facts:
        expected_kind = "contradiction" if fact.salience == "high" else "canonical"
        expected_id = f"{fact.id}:{expected_kind}"
        stale_kind = "canonical" if expected_kind == "contradiction" else "contradiction"
        stale_id = f"{fact.id}:{stale_kind}"
        for query_type, query in (
            ("direct", fact.direct_query),
            ("paraphrase", fact.paraphrase_query),
            ("decoy", fact.decoy_query),
        ):
            scored = sorted(
                (
                    (_cosine(embeddings[query], embeddings[item["text"]]), item)
                    for item in candidates
                ),
                key=lambda pair: pair[0],
                reverse=True,
            )[:20]
            spread = scored[0][0] - scored[-1][0]
            candidate_rows = []
            for rank, (similarity, candidate) in enumerate(scored, start=1):
                positive = query_type != "decoy" and candidate["id"] == expected_id
                candidate_rows.append(
                    {
                        "candidate_id": candidate["id"],
                        "similarity": similarity,
                        "features": _features(
                            query,
                            candidate,
                            similarity=similarity,
                            rank=rank,
                            score_spread=spread,
                        ),
                        "label": float(positive),
                        "hard_negative": bool(
                            not positive
                            and (
                                candidate["id"] == stale_id
                                or (
                                    query_type == "decoy"
                                    and candidate["fact_id"] == fact.id
                                )
                            )
                        ),
                    }
                )
            rows.append(
                {
                    "fact_id": fact.id,
                    "query_type": query_type,
                    "expected_id": expected_id,
                    "stale_id": stale_id,
                    "candidates": candidate_rows,
                }
            )
    return rows


def _balanced_training(rows: list[dict], seed: int) -> tuple[np.ndarray, np.ndarray]:
    positives = [item for row in rows for item in row["candidates"] if item["label"] == 1.0]
    negatives = [item for row in rows for item in row["candidates"] if item["label"] == 0.0]
    hard_negatives = [item for item in negatives if item.get("hard_negative")]
    if not positives:
        raise ValueError("training split contains no positive candidates")
    rng = np.random.RandomState(seed)
    negative_pool = hard_negatives or negatives
    negative_indices = rng.choice(
        len(negative_pool),
        size=len(positives),
        replace=len(negative_pool) < len(positives),
    )
    balanced = positives + [negative_pool[index] for index in negative_indices]
    rng.shuffle(balanced)
    return (
        np.asarray([item["features"] for item in balanced], dtype=np.float32),
        np.asarray([[item["label"]] for item in balanced], dtype=np.float32),
    )


def _network(seed: int, feature_count: int) -> ModernSubgroupedRTRL:
    state = np.random.get_state()
    try:
        np.random.seed(seed)
        return ModernSubgroupedRTRL(
            RTRLConfig(
                num_inputs=feature_count,
                num_outputs=1,
                num_hidden=8,
                time_delay=0,
                epochs=40,
                lr=0.003,
                optimizer="adam",
                grad_clip_norm=1.0,
                gated=True,
                hidden_activation="tanh",
                output_activation="sigmoid",
                categorical_output=False,
                continuous_epochs=False,
                device="cpu",
                verbose=False,
            )
        )
    finally:
        np.random.set_state(state)


def _evaluate(rows: list[dict], network: ModernSubgroupedRTRL, weight: float) -> dict:
    counts = defaultdict(int)
    for row in rows:
        features = np.asarray([item["features"] for item in row["candidates"]])
        utility = network.predict(features)[:, 0]
        similarities = [float(item["similarity"]) for item in row["candidates"]]
        spread = max(similarities) - min(similarities)
        adjusted = [
            similarity + weight * (float(score) - 0.5) * spread
            for similarity, score in zip(similarities, utility)
        ]
        base_top = [item["candidate_id"] for item in row["candidates"][:3]]
        order = np.argsort(np.asarray(adjusted))[::-1][:3]
        neural_top = [row["candidates"][index]["candidate_id"] for index in order]
        query_type = row["query_type"]
        counts[f"{query_type}_queries"] += 1
        if query_type == "decoy":
            counts["base_decoy_rejected"] += int(row["expected_id"] not in base_top)
            counts["neural_decoy_rejected"] += int(row["expected_id"] not in neural_top)
        else:
            counts["base_recalled"] += int(row["expected_id"] in base_top)
            counts["neural_recalled"] += int(row["expected_id"] in neural_top)
            counts["non_decoy_queries"] += 1
        counts["base_stale"] += int(row["stale_id"] in base_top)
        counts["neural_stale"] += int(row["stale_id"] in neural_top)
    total = len(rows)
    non_decoy = counts["non_decoy_queries"]
    decoys = counts["decoy_queries"]
    return {
        "weight": weight,
        "base_recall": counts["base_recalled"] / non_decoy,
        "neural_recall": counts["neural_recalled"] / non_decoy,
        "base_decoy_rejection": counts["base_decoy_rejected"] / decoys,
        "neural_decoy_rejection": counts["neural_decoy_rejected"] / decoys,
        "base_stale_rate": counts["base_stale"] / total,
        "neural_stale_rate": counts["neural_stale"] / total,
    }


def run(args: argparse.Namespace) -> dict:
    corpus = FactCorpus.load(args.corpus)
    texts = []
    for fact in corpus.facts:
        texts.extend(
            [
                fact.canonical,
                fact.contradiction,
                fact.direct_query,
                fact.paraphrase_query,
                fact.decoy_query,
            ]
        )
    texts.extend(
        f"Distractor {index}: The quarterly budget review showed a 3.2% variance "
        f"in line item {index % 50 + 1}. The audit committee noted this for follow-up."
        for index in range(200)
    )
    embeddings = _embed_texts(
        list(dict.fromkeys(texts)),
        cache_path=Path(args.embedding_cache),
        model=args.embed_model,
        base_url=args.ollama_url,
    )
    rows = build_dataset(corpus, embeddings)
    fact_ids = [fact.id for fact in corpus.facts]
    held_out = set(fact_ids[::3])
    training_rows = [row for row in rows if row["fact_id"] not in held_out]
    test_rows = [row for row in rows if row["fact_id"] in held_out]
    reports = []
    for seed in args.seeds:
        data, targets = _balanced_training(training_rows, seed)
        network = _network(seed, data.shape[1])
        history = network.train(data, targets)
        reports.append(
            {
                "seed": seed,
                "training_examples": len(data),
                "initial_error": history[0]["avg_error"],
                "final_error": history[-1]["avg_error"],
                "weights": [
                    _evaluate(test_rows, network, weight)
                    for weight in args.weights
                ],
            }
        )
    result = {
        "held_out_facts": sorted(held_out),
        "feature_names": [
            "similarity",
            "reciprocal_rank",
            "score_spread",
            "lexical_jaccard",
            "importance",
            "recency",
            "repetition",
            "length_ratio",
        ],
        "seeds": reports,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        default=str(Path(__file__).resolve().parent / "eval_corpus.json"),
    )
    parser.add_argument("--embedding-cache", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--embed-model", default="nomic-embed-text")
    parser.add_argument("--seeds", type=lambda raw: [int(x) for x in raw.split(",")], default=[0, 1, 2])
    parser.add_argument("--weights", type=lambda raw: [float(x) for x in raw.split(",")], default=[0.05, 0.1, 0.2])
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
