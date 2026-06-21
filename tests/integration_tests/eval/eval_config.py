"""Configuration for the neural-on versus baseline memory evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


TRIAL_SCHEDULE = (
    ("baseline", "all", 1, 0),
    ("reinforce_3x", "high_salience", 3, 2),
    ("reinforce_8x", "high_salience", 5, 2),
    ("contradict", "contradictions", 1, 1),
    ("forgetting", "none", 0, 200),
    ("cold_query", "none", 0, 0),
)


@dataclass
class EvalConfig:
    backends: tuple[str, ...] = ("baseline", "neural_on")
    schedule: list[tuple[str, str, int, int]] = field(
        default_factory=lambda: list(TRIAL_SCHEDULE)
    )
    retrieve_top_k: int = 3
    mode: str = "retrieval"
    warmup_replays: int = 1
    neural_min_warmup_steps: int = 50
    judge_model: str = "qwen3:8b"
    answer_model: str | None = None
    judge_base_url: str = "http://localhost:11434"
    judge_timeout_sec: float = 120.0
    judge_retries: int = 2
    judge_concurrency: int = 4
    judge_max_tokens: int = 384
    embed_model: str = "nomic-embed-text"
    embed_base_url: str = "http://localhost:11434"
    affinity_weight: float = 0.15
    project_id: str = "neural_ab_eval"
    output_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent / "runs"
    )
    corpus_path: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent / "eval_corpus.json"
    )

    def validate_backend(self, backend: str) -> None:
        if backend not in self.backends:
            raise ValueError(
                f"Unknown backend {backend!r}; expected one of {self.backends}"
            )

    def validate_mode(self) -> None:
        if self.mode not in {"retrieval", "generation"}:
            raise ValueError(
                f"Unknown mode {self.mode!r}; expected retrieval or generation"
            )
