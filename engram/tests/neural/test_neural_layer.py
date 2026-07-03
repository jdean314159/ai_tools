from __future__ import annotations

import numpy as np

from engram import (
    MemoryLayer,
    MemoryObservation,
    ProjectMemory,
    RecallQuery,
)
from engram.embeddings.base import BatchEmbeddingResult, EmbeddingResult
from engram.neural import NeuralMemoryConfig, NeuralMemoryLayer


class StaticEmbedder:
    dimension = 8
    model_name = "static:test"

    def __init__(self) -> None:
        eye = np.eye(self.dimension, dtype=np.float32)
        self.vectors = {
            "query": eye[0],
            "matching answer": eye[1],
            "query matching answer": eye[1],
            "query unrelated answer": eye[2],
            "unrelated answer": eye[2],
        }

    def _vector(self, text: str) -> np.ndarray:
        return self.vectors.get(text, np.eye(self.dimension, dtype=np.float32)[3])

    def embed(self, text: str) -> EmbeddingResult:
        vector = self._vector(text)
        return EmbeddingResult(
            text=text,
            embedding=vector.tolist(),
            model=self.model_name,
            dimension=self.dimension,
        )

    def embed_batch(self, texts: list[str]) -> BatchEmbeddingResult:
        return BatchEmbeddingResult(
            texts=texts,
            embeddings=[self._vector(text).tolist() for text in texts],
            model=self.model_name,
            dimension=self.dimension,
        )


def _config(*, affinity_weight: float = 0.15) -> NeuralMemoryConfig:
    return NeuralMemoryConfig(
        key_dim=8,
        value_dim=4,
        hidden_dim=8,
        embedding_dim=8,
        lr=0.003,
        grad_clip_norm=1.0,
        surprise_threshold=0.0,
        affinity_weight=affinity_weight,
        prompt_advisory_enabled=True,
        device="cpu",
    )


def _train_pair(layer: NeuralMemoryLayer, count: int = 100) -> None:
    for _ in range(count):
        layer.observe(MemoryObservation("user", "query", "s1"))
        layer.observe(MemoryObservation("assistant", "matching answer", "s1"))


def test_layer_implements_memory_layer_protocol_and_disables_reranking():
    embedder = StaticEmbedder()
    layer = NeuralMemoryLayer(
        embedder=embedder,
        project_dir=None,
        config=_config(),
        candidate_resolver=lambda candidate_id: embedder.vectors[candidate_id],
    )

    assert isinstance(layer, MemoryLayer)
    contribution = layer.contribute_to_recall(
        RecallQuery(
            query="query",
            embedding=tuple(embedder.vectors["query"]),
            metadata={"candidate_ids": ("matching answer", "unrelated answer")},
        )
    )

    assert contribution is None


def test_last_surprise_requires_a_complete_pair():
    layer = NeuralMemoryLayer(StaticEmbedder(), None, _config())

    assert layer.last_surprise() is None
    layer.observe(MemoryObservation("user", "query", "s1"))
    assert layer.last_surprise() is None
    layer.observe(MemoryObservation("assistant", "matching answer", "s1"))

    surprise = layer.last_surprise()
    assert isinstance(surprise, float)
    assert surprise > 0.0
    assert layer.get_last_surprise() == surprise


def test_prompt_hint_requires_warmup():
    layer = NeuralMemoryLayer(StaticEmbedder(), None, _config())
    query = RecallQuery(query="query")

    assert layer.contribute_to_prompt(query) is None

    _train_pair(layer, count=50)
    hint = layer.contribute_to_prompt(query)

    assert hint is not None
    assert hint.text
    assert hint.metadata["warmed_up"] is True


def test_persisted_layer_reloads_training_state(tmp_path):
    embedder = StaticEmbedder()
    first = NeuralMemoryLayer(embedder, tmp_path, _config())
    _train_pair(first, count=30)
    first.persist()

    restored = NeuralMemoryLayer(embedder, tmp_path, _config())

    assert first.get_stats()["total_steps"] == 30
    assert restored.get_stats()["total_steps"] == 30
    assert restored.contribute_to_recall(RecallQuery(query="query")) is None


def test_project_memory_neural_does_not_change_retrieval_order(tmp_path):
    embedder = StaticEmbedder()
    baseline = ProjectMemory(
        base_dir=tmp_path / "baseline",
        project_id="p",
        session_id="s1",
        embedder=embedder,
        enable_semantic_graph=False,
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    neural = ProjectMemory(
        base_dir=tmp_path / "neural",
        project_id="p",
        session_id="s1",
        embedder=embedder,
        enable_semantic_graph=False,
        auto_ingest_turns=False,
        auto_pair_assistant=False,
        enable_neural=True,
        neural_config=_config(),
    )

    try:
        for memory in (baseline, neural):
            memory.store_episode(
                "query unrelated answer",
                importance=0.52,
                bypass_filter=True,
                bypass_dedup=True,
            )
            memory.store_episode(
                "query matching answer",
                importance=0.50,
                bypass_filter=True,
                bypass_dedup=True,
            )
            # Exercise the resolver's JSONL/text fallback deterministically.
            memory.chromadb = None

        baseline_ranked = baseline.search_episodes("query", n=2)
        assert baseline_ranked[0].text.endswith(
            "unrelated answer"
        )
        assert neural.neural_layer is not None
        _train_pair(neural.neural_layer)
        ranked = neural.search_episodes("query", n=2)

        assert [item.text for item in ranked] == [
            item.text for item in baseline_ranked
        ]
    finally:
        baseline.close()
        neural.close()


def test_neural_is_default_off_and_requires_embedder(caplog):
    default = ProjectMemory(session_id="s1")
    requested_without_embedder = ProjectMemory(
        session_id="s1",
        enable_neural=True,
    )

    try:
        assert default.neural_layer is None
        assert requested_without_embedder.neural_layer is None
        assert default.get_stats()["config"]["neural_enabled"] is False
        assert "requested without an embedder" in caplog.text
    finally:
        default.close()
        requested_without_embedder.close()


def test_project_memory_threads_affinity_weight_to_neural_layer(tmp_path):
    config = _config(affinity_weight=0.3)
    memory = ProjectMemory(
        base_dir=tmp_path,
        project_id="p",
        embedder=StaticEmbedder(),
        enable_semantic_graph=False,
        enable_neural=True,
        neural_config=config,
    )

    try:
        assert memory.neural_layer is not None
        assert memory.neural_layer.config.affinity_weight == 0.3
        assert memory.neural_layer._affinity_weight == 0.3
    finally:
        memory.close()


def test_surprise_adjusts_episode_importance_in_memory_and_jsonl(tmp_path):
    class ControlledSurpriseLayer:
        name = "controlled-surprise"

        def observe(self, observation):
            del observation

        def last_surprise(self):
            return 3.0

        def importance_adjustment_enabled(self):
            return True

        def contribute_to_recall(self, query):
            del query
            return None

        def contribute_to_prompt(self, query):
            del query
            return None

        def warmup(self, history):
            del history

        def persist(self):
            return None

        def close(self):
            return None

    memory = ProjectMemory(
        base_dir=tmp_path,
        project_id="p",
        enable_semantic_graph=False,
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    memory.register_layer(ControlledSurpriseLayer())

    try:
        episode_id = memory.store_episode(
            "A sufficiently detailed novel episode for deterministic storage.",
            importance=0.5,
            bypass_filter=True,
        )

        episode = next(
            item for item in memory._episodes if item["id"] == episode_id
        )
        persisted = memory._read_jsonl(memory._episodes_path)
        persisted_episode = next(
            item for item in persisted if item["id"] == episode_id
        )
        assert episode["importance"] == 0.8
        assert persisted_episode["importance"] == 0.8
    finally:
        memory.close()


def test_surprise_does_not_adjust_importance_without_explicit_opt_in(tmp_path):
    class TelemetryOnlyLayer:
        name = "telemetry-only"

        def observe(self, observation):
            del observation

        def last_surprise(self):
            return 3.0

        def contribute_to_recall(self, query):
            del query
            return None

        def contribute_to_prompt(self, query):
            del query
            return None

        def warmup(self, history):
            del history

        def persist(self):
            return None

        def close(self):
            return None

    memory = ProjectMemory(
        base_dir=tmp_path,
        project_id="p",
        enable_semantic_graph=False,
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    memory.register_layer(TelemetryOnlyLayer())

    try:
        episode_id = memory.store_episode(
            "A sufficiently detailed novel episode for deterministic storage.",
            importance=0.5,
            bypass_filter=True,
        )
        episode = next(
            item for item in memory._episodes if item["id"] == episode_id
        )

        assert episode["importance"] == 0.5
    finally:
        memory.close()
