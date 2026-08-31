"""MemoryLayer adapter for the optional RTRL/TITANS neural memory."""

from __future__ import annotations

import logging
import math
from collections import deque
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..contracts import MemoryObservation, PromptHint, RecallContribution, RecallQuery
from .neural_memory import EmbeddingProjector, NeuralMemory, NeuralMemoryConfig

logger = logging.getLogger(__name__)

CandidateResolver = Callable[[str], np.ndarray | None]
EpisodeProvider = Callable[[int], list[tuple[str, np.ndarray, str]]]


def _build_context_hint(
    top_episodes: list[dict[str, Any]],
    surprise: float | None,
    ema: float | None,
    trajectory: str | None,
) -> str | None:
    """Build a deterministic natural-language summary of neural context."""
    if not top_episodes and trajectory is None:
        return None

    lines = ["[Neural context]"]
    if trajectory:
        ratio = (
            float(surprise) / float(ema)
            if surprise is not None and ema is not None and ema > 0
            else 1.0
        )
        if trajectory == "converging":
            label = "Familiar pattern"
            suffix = ", converging"
        elif trajectory == "diverging":
            label = "Shifting pattern"
            suffix = ", diverging"
        else:
            label = "Stable pattern"
            suffix = ""
        lines.append(f"{label} (surprise {ratio:.1f}x baseline{suffix}).")

    if top_episodes:
        lines.append("Network predicts relevance to:")
        for episode in top_episodes[:3]:
            snippet = str(episode.get("text", ""))[:80].replace("\n", " ")
            if snippet:
                lines.append(f"- {snippet}")

    return "\n".join(lines) if len(lines) > 1 else None


class NeuralMemoryLayer:
    """Adapt neural associative memory to Engram's additive extension seam."""

    name = "neural"

    def __init__(
        self,
        embedder: Any,
        project_dir: str | Path | None,
        config: NeuralMemoryConfig | None = None,
        candidate_resolver: CandidateResolver | None = None,
        episode_provider: EpisodeProvider | None = None,
    ) -> None:
        if embedder is None:
            raise ValueError("NeuralMemoryLayer requires an embedder")

        self.config = config or NeuralMemoryConfig()
        self._embedder = embedder
        self._candidate_resolver = candidate_resolver
        self._episode_provider = episode_provider
        self._affinity_weight = float(self.config.affinity_weight)
        if not math.isfinite(self._affinity_weight):
            raise ValueError("config.affinity_weight must be finite")
        logger.info(
            "Inactive neural affinity compatibility value: %.3f",
            self._affinity_weight,
        )

        embedding_dim = int(getattr(embedder, "dimension", self.config.embedding_dim))
        self.config.embedding_dim = embedding_dim
        self._key_projector = EmbeddingProjector(
            embedding_dim,
            self.config.key_dim,
            seed=self.config.projection_seed,
        )
        self._value_projector = EmbeddingProjector(
            embedding_dim,
            self.config.value_dim,
            seed=self.config.projection_seed,
        )
        self._neural = NeuralMemory(
            project_dir=Path(project_dir) if project_dir is not None else None,
            config=self.config,
        )
        self._pending_user_key: np.ndarray | None = None
        self._last_surprise: float | None = None
        self._surprise_window: deque[float] = deque(maxlen=10)
        self._closed = False
        self._dirty = False

    def _embedding(self, text: str) -> np.ndarray | None:
        if not str(text or "").strip():
            return None
        result = self._embedder.embed(str(text))
        value = getattr(result, "embedding", result)
        if value is None:
            return None
        embedding = np.asarray(value, dtype=np.float32)
        if embedding.ndim != 1 or embedding.size != self.config.embedding_dim:
            raise ValueError(
                "embedder returned dimension "
                f"{embedding.size}, expected {self.config.embedding_dim}"
            )
        return embedding

    def _query_embedding(self, query: RecallQuery) -> np.ndarray | None:
        if query.embedding is not None:
            embedding = np.asarray(query.embedding, dtype=np.float32)
            if embedding.ndim != 1 or embedding.size != self.config.embedding_dim:
                raise ValueError(
                    "query embedding dimension "
                    f"{embedding.size}, expected {self.config.embedding_dim}"
                )
            return embedding
        return self._embedding(query.query)

    def read_as_embedding(
        self,
        query_embedding: np.ndarray,
    ) -> np.ndarray | None:
        """Read neural prediction back into approximate embedding space."""
        stats = self._neural.get_stats()
        if not bool(stats.get("healthy", True)):
            return None
        if int(stats.get("total_steps", 0)) < int(self.config.min_warmup_steps):
            return None
        query = np.asarray(query_embedding, dtype=np.float32)
        if query.ndim != 1 or query.size != self.config.embedding_dim:
            raise ValueError(
                f"query embedding dimension {query.size}, expected {self.config.embedding_dim}"
            )
        value = self._neural.read(self._key_projector(query))
        return self._value_projector.pseudoinverse() @ value

    def _surprise_trajectory(self) -> str | None:
        """Classify recent prediction error as converging, diverging, or stable."""
        if len(self._surprise_window) < 5:
            return None
        recent = list(self._surprise_window)
        midpoint = len(recent) // 2
        first_half = sum(recent[:midpoint]) / midpoint
        second_half = sum(recent[midpoint:]) / (len(recent) - midpoint)
        delta = second_half - first_half
        if delta < -0.1:
            return "converging"
        if delta > 0.1:
            return "diverging"
        return "stable"

    def _find_aligned_episodes(
        self,
        approx_embedding: np.ndarray,
        *,
        k: int = 3,
        candidate_limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self._episode_provider is None:
            return []
        approx = np.asarray(approx_embedding, dtype=np.float32)
        approx_norm = float(np.linalg.norm(approx))
        if approx_norm < 1e-10:
            return []

        aligned: list[dict[str, Any]] = []
        for episode_id, embedding, text in self._episode_provider(candidate_limit):
            candidate = np.asarray(embedding, dtype=np.float32)
            if candidate.ndim != 1 or candidate.size != approx.size:
                continue
            candidate_norm = float(np.linalg.norm(candidate))
            if candidate_norm < 1e-10:
                continue
            similarity = float(np.dot(approx, candidate) / (approx_norm * candidate_norm))
            if math.isfinite(similarity):
                aligned.append(
                    {
                        "id": str(episode_id),
                        "text": str(text),
                        "similarity": similarity,
                    }
                )
        aligned.sort(key=lambda item: item["similarity"], reverse=True)
        return aligned[: max(0, int(k))]

    def _neural_context(self, query_embedding: np.ndarray) -> dict[str, Any]:
        stats = self._neural.get_stats()
        return {
            "last_surprise": self._last_surprise,
            "surprise_ema": float(stats.get("surprise_ema", 0.0)),
            "avg_surprise": float(stats.get("avg_surprise", 0.0)),
            "total_steps": int(stats.get("total_steps", 0)),
            "trajectory": self._surprise_trajectory(),
            "warmed_up": (int(stats.get("total_steps", 0)) >= int(self.config.min_warmup_steps)),
        }

    def observe(self, observation: MemoryObservation) -> None:
        role = str(observation.role or "").strip().lower()
        if role not in {"user", "assistant"}:
            return

        embedding = (
            np.asarray(observation.embedding, dtype=np.float32)
            if observation.embedding is not None
            else self._embedding(observation.text)
        )
        if embedding is None:
            return
        if embedding.ndim != 1 or embedding.size != self.config.embedding_dim:
            raise ValueError(
                "observation embedding dimension "
                f"{embedding.size}, expected {self.config.embedding_dim}"
            )

        if role == "user":
            self._pending_user_key = self._key_projector(embedding)
            return

        if self._pending_user_key is None:
            return
        value = self._value_projector(embedding)
        result = self._neural.step(self._pending_user_key, value)
        self._pending_user_key = None
        if not bool(result.get("healthy", True)):
            self._last_surprise = None
            self._surprise_window.clear()
            return
        self._last_surprise = float(result["surprise"])
        self._surprise_window.append(self._last_surprise)
        self._dirty = True

    def contribute_to_recall(
        self,
        query: RecallQuery,
    ) -> RecallContribution | None:
        # Neural memory influences write-side importance, not retrieval order.
        # Query context remains available through contribute_to_prompt().
        del query
        return None

    def contribute_to_prompt(self, query: RecallQuery) -> PromptHint | None:
        if not self.config.prompt_advisory_enabled:
            return None
        query_embedding = self._query_embedding(query)
        if query_embedding is None:
            return None
        approx_embedding = self.read_as_embedding(query_embedding)
        if approx_embedding is None:
            return None

        context = self._neural_context(query_embedding)
        top_episodes = self._find_aligned_episodes(approx_embedding)
        context["aligned_episodes"] = top_episodes
        text = _build_context_hint(
            top_episodes,
            self._last_surprise,
            float(context["surprise_ema"]),
            str(context["trajectory"]) if context["trajectory"] else None,
        )
        if not text:
            return None
        return PromptHint(text=text, metadata=context)

    def warmup(self, history: list[MemoryObservation]) -> None:
        for observation in history:
            self.observe(observation)

    def persist(self) -> None:
        self._neural.save()
        self._dirty = False

    def get_last_surprise(self) -> float | None:
        """Return prediction error from the most recent paired RTRL step."""
        return self._last_surprise

    def last_surprise(self) -> float | None:
        """Return surprise from the most recent completed observation pair."""
        return self.get_last_surprise()

    def importance_adjustment_enabled(self) -> bool:
        """Whether surprise may influence stored episode importance."""
        return bool(self.config.importance_advisory_enabled)

    def close(self) -> None:
        if self._closed:
            return
        if self._dirty:
            self.persist()
        self._closed = True

    def get_stats(self) -> dict[str, Any]:
        stats = self._neural.get_stats()
        stats["last_surprise"] = self._last_surprise
        stats["surprise_trajectory"] = self._surprise_trajectory()
        return stats
