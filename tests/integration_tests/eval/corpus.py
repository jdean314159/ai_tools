"""Bundled fact corpus models for the neural memory A/B evaluation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Fact:
    id: str
    category: str
    salience: str
    canonical: str
    contradiction: str
    direct_query: str
    paraphrase_query: str
    decoy_query: str
    expected_snippet: str
    injected_count: int = 0
    last_injected_trial: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class FactCorpus:
    def __init__(self, facts: list[Fact]):
        self.facts = facts
        self._by_id = {fact.id: fact for fact in facts}

    def subset(self, label: str) -> list[Fact]:
        if label == "all":
            return self.facts
        if label in {"high_salience", "contradictions"}:
            return [fact for fact in self.facts if fact.salience == "high"]
        if label == "none":
            return []
        return [fact for fact in self.facts if fact.category == label]

    def by_id(self, fact_id: str) -> Fact:
        return self._by_id[fact_id]

    def limited(self, limit: int | None) -> "FactCorpus":
        if limit is None:
            return self
        return FactCorpus(self.facts[: max(0, int(limit))])

    @classmethod
    def load(cls, path: str | Path) -> "FactCorpus":
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Fact(**row) for row in rows])

    def __len__(self) -> int:
        return len(self.facts)
