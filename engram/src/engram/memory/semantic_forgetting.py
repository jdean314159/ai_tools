from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ForgettingConfig:
    enable_decay: bool = True
    decay_rate: float = 0.95
    decay_period_days: int = 7
    enable_pruning: bool = True
    min_confidence: float = 0.1
    min_age_days: int = 30
    max_prune_per_run: int = 100
    enable_superseded_cleanup: bool = True
    superseded_age_days: int = 90

    def __post_init__(self):
        if not 0.0 <= self.decay_rate <= 1.0:
            raise ValueError(f"decay_rate must be 0.0-1.0, got {self.decay_rate}")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError(f"min_confidence must be 0.0-1.0, got {self.min_confidence}")


class ForgettingPolicy:
    def __init__(self, config: Optional[ForgettingConfig] = None):
        self.config = config or ForgettingConfig()

    def run_maintenance(self, graph) -> Dict[str, Any]:
        stats: Dict[str, Any] = {"decayed": 0, "pruned": 0, "superseded_removed": 0}

        if self.config.enable_decay:
            graph.decay_importance(
                decay_rate=self.config.decay_rate,
                period_days=self.config.decay_period_days,
            )
            stats["decayed"] = 1

        if self.config.enable_pruning:
            stats["pruned"] = graph.forget_low_importance_facts(
                min_confidence=self.config.min_confidence,
                min_age_days=self.config.min_age_days,
                max_to_prune=self.config.max_prune_per_run,
            )

        if self.config.enable_superseded_cleanup:
            stats["superseded_removed"] = graph.forget_superseded_facts(
                min_age_days=self.config.superseded_age_days,
            )

        graph.save()
        logger.info(f"Forgetting maintenance: {stats}")
        return stats
