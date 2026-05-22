from __future__ import annotations
import math
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have same dimension")
    dot = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def detect_contradiction(
    new_fact: Dict[str, Any],
    existing_facts: List[Dict[str, Any]],
    embedder=None,
    similarity_threshold: float = 0.85,
) -> Optional[str]:
    """Return ID of contradicted fact, or None."""
    new_subject = new_fact.get("subject", "").lower()
    new_value = new_fact.get("value", "").lower()

    for existing in existing_facts:
        if new_fact.get("fact_type") != existing.get("fact_type"):
            continue

        existing_subject = existing.get("subject", "").lower()
        existing_value = existing.get("value", "").lower()

        subject_match = (new_subject == existing_subject)

        if not subject_match and embedder:
            try:
                sim = cosine_similarity(
                    embedder.embed(new_subject).embedding,
                    embedder.embed(existing_subject).embedding,
                )
                subject_match = sim >= similarity_threshold
            except Exception as e:
                logger.debug(f"Embedding similarity failed: {e}")

        if subject_match and new_value != existing_value:
            logger.info(
                f"Contradiction: {existing_subject} was '{existing_value}', now '{new_value}'"
            )
            return existing.get("id")

    return None
