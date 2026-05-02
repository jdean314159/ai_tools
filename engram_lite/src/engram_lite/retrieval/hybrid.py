from __future__ import annotations
import time
from typing import Any, Dict, List, Optional


def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    k: int = 60,
    id_key: str = "id",
) -> List[Dict[str, Any]]:
    """Combine ranked lists using Reciprocal Rank Fusion (RRF).

    score = sum(1 / (k + rank)) across all lists.
    k=60 from original paper; configurable.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            item_id = item.get(id_key)
            if item_id is None:
                continue
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
            if item_id not in items:
                items[item_id] = item

    return [
        {**items[iid], "rrf_score": score}
        for iid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]


def hybrid_episode_search(
    query: str,
    query_embedding: Optional[List[float]],
    *,
    vector_results: Optional[List[Dict[str, Any]]] = None,
    text_results: Optional[List[Dict[str, Any]]] = None,
    recency_boost: bool = True,
    importance_boost: bool = True,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """Combine vector and text search via RRF with optional boosts."""
    ranked_lists = []
    if vector_results:
        ranked_lists.append(vector_results)
    if text_results:
        ranked_lists.append(text_results)
    if not ranked_lists:
        return []

    fused = reciprocal_rank_fusion(ranked_lists, k=k, id_key="id")

    now = time.time()
    for item in fused:
        score = item["rrf_score"]

        if recency_boost and "created_at" in item:
            age_days = (now - float(item["created_at"])) / 86400.0
            score *= max(0.5, 1.0 - (age_days / 30.0))

        if importance_boost and "importance" in item:
            importance = float(item.get("importance", 0.5))
            score *= 0.8 + importance * 0.4  # range [0.8, 1.2]

        item["final_score"] = score

    fused.sort(key=lambda x: x["final_score"], reverse=True)
    return fused
