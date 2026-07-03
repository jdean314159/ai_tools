from __future__ import annotations

import time

import numpy as np

from engram import MemoryObservation, ProjectMemory, RecallQuery
from engram.embeddings.base import BatchEmbeddingResult, EmbeddingResult
from engram.neural import NeuralMemoryConfig, NeuralMemoryLayer
from engram.neural.coordinator import _build_context_hint
from engram.neural.neural_memory import EmbeddingProjector, NeuralMemory


class ContextEmbedder:
    dimension = 8
    model_name = "context:test"

    def embed(self, text: str) -> EmbeddingResult:
        seed = sum(ord(char) for char in text) % self.dimension
        vector = np.zeros(self.dimension, dtype=np.float32)
        vector[seed] = 1.0
        return EmbeddingResult(
            text=text,
            embedding=vector.tolist(),
            model=self.model_name,
            dimension=self.dimension,
        )

    def embed_batch(self, texts: list[str]) -> BatchEmbeddingResult:
        return BatchEmbeddingResult(
            texts=texts,
            embeddings=[self.embed(text).embedding for text in texts],
            model=self.model_name,
            dimension=self.dimension,
        )


def _config(**overrides) -> NeuralMemoryConfig:
    values = {
        "key_dim": 8,
        "value_dim": 32,
        "hidden_dim": 8,
        "embedding_dim": 8,
        "min_warmup_steps": 2,
        "prompt_advisory_enabled": True,
        "surprise_threshold": 0.0,
        "device": "cpu",
    }
    values.update(overrides)
    return NeuralMemoryConfig(**values)


def _pair(layer: NeuralMemoryLayer, index: int) -> None:
    layer.observe(MemoryObservation("user", f"question {index}", "s1"))
    layer.observe(MemoryObservation("assistant", f"answer {index}", "s1"))


def test_shape_mismatch_discards_stale_saved_state(tmp_path, caplog):
    old = NeuralMemory(
        tmp_path,
        _config(value_dim=16, config_version=1),
    )
    old.step(np.ones(8, dtype=np.float32), np.ones(16, dtype=np.float32))
    old.save()

    current = NeuralMemory(tmp_path, _config(value_dim=32))

    assert current._memory is not None
    assert current._memory.config.value_dim == 32
    assert current.get_stats()["total_steps"] == 0
    assert "weight shape mismatch" in caplog.text


def test_embedding_projector_pseudoinverse_is_cached():
    projector = EmbeddingProjector(768, 64)

    first = projector.pseudoinverse()
    second = projector.pseudoinverse()

    assert first.shape == (768, 64)
    assert second is first


def test_read_as_embedding_requires_configured_warmup():
    layer = NeuralMemoryLayer(ContextEmbedder(), None, _config())
    query = np.asarray(ContextEmbedder().embed("query").embedding)

    assert layer.read_as_embedding(query) is None
    _pair(layer, 0)
    _pair(layer, 1)

    reconstructed = layer.read_as_embedding(query)
    assert reconstructed is not None
    assert reconstructed.shape == (ContextEmbedder.dimension,)


def test_surprise_trajectory_classifies_recent_values():
    layer = NeuralMemoryLayer(ContextEmbedder(), None, _config())

    layer._surprise_window.extend([1.0, 0.9, 0.8, 0.5, 0.4])
    assert layer._surprise_trajectory() == "converging"
    layer._surprise_window.clear()
    layer._surprise_window.extend([0.2, 0.3, 0.4, 0.8, 0.9])
    assert layer._surprise_trajectory() == "diverging"
    layer._surprise_window.clear()
    layer._surprise_window.extend([0.5, 0.5, 0.5, 0.5, 0.5])
    assert layer._surprise_trajectory() == "stable"


def test_context_hint_is_template_only_and_bounded_to_three_episodes():
    hint = _build_context_hint(
        [{"text": f"episode {index}"} for index in range(5)],
        surprise=0.5,
        ema=1.0,
        trajectory="converging",
    )

    assert hint is not None
    assert "[Neural context]" in hint
    assert "episode 0" in hint
    assert "episode 3" not in hint
    assert _build_context_hint([], None, None, None) is None


def test_prompt_advisory_is_default_off():
    layer = NeuralMemoryLayer(
        ContextEmbedder(),
        None,
        _config(prompt_advisory_enabled=False, min_warmup_steps=0),
    )

    assert layer.contribute_to_prompt(RecallQuery(query="question")) is None
    assert layer.importance_adjustment_enabled() is False


def test_project_memory_prompt_contains_synthesized_context(tmp_path):
    memory = ProjectMemory(
        base_dir=tmp_path,
        project_id="context",
        session_id="s1",
        embedder=ContextEmbedder(),
        enable_neural=True,
        neural_config=_config(),
        enable_semantic_graph=False,
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    try:
        memory.store_episode(
            "The deployment region is west.",
            importance=0.7,
            bypass_filter=True,
        )
        for index in range(2):
            memory.add_turn("user", f"question {index}", "s1")
            memory.add_turn("assistant", f"answer {index}", "s1")

        result = memory.build_prompt("Which deployment region is used?")
        hint = memory.neural_layer.contribute_to_prompt(
            RecallQuery(query="Which deployment region is used?")
        )

        assert "[Neural context]" in result["prompt"]
        assert "Network predicts relevance to:" in result["prompt"]
        assert hint is not None
        assert hint.metadata["aligned_episodes"]
        assert hint.metadata["aligned_episodes"][0]["text"] == (
            "The deployment region is west."
        )
    finally:
        memory.close()


def test_warm_layers_replays_persisted_session_pairs(tmp_path):
    first = ProjectMemory(
        base_dir=tmp_path,
        project_id="warmup",
        session_id="s1",
        enable_semantic_graph=False,
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    first.add_turn("user", "stored question", "s1")
    first.add_turn("assistant", "stored answer", "s1")
    first.close()

    second = ProjectMemory(
        base_dir=tmp_path,
        project_id="warmup",
        session_id="s2",
        embedder=ContextEmbedder(),
        enable_neural=True,
        neural_config=_config(min_warmup_steps=1),
        enable_semantic_graph=False,
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    try:
        assert second.neural_layer is not None
        assert second.neural_layer.get_stats()["total_steps"] == 0

        second.warm_layers_from_history()

        assert second.neural_layer.get_stats()["total_steps"] == 1
    finally:
        second.close()


def test_advisory_hint_is_capped_without_reserved_budget():
    memory = ProjectMemory(token_counter=lambda text: len(text.split()))
    text = " ".join(f"token-{index}" for index in range(250))

    capped = memory._cap_hint_text(text, max_tokens=200)

    assert len(capped.split()) <= 200
    assert capped.endswith("...")


def test_value_dim_32_remains_finite_at_evaluation_volume():
    memory = NeuralMemory(
        config=_config(
            key_dim=64,
            value_dim=32,
            hidden_dim=32,
            embedding_dim=64,
        )
    )
    rng = np.random.RandomState(7)
    steps = 600
    started = time.perf_counter()

    for _ in range(steps):
        memory.step(
            rng.randn(64).astype(np.float32),
            rng.randn(32).astype(np.float32),
        )
    per_step_ms = ((time.perf_counter() - started) * 1000) / steps

    assert memory._memory is not None
    weights = memory._memory.B.to_numpy(memory._memory.net.weights)
    assert np.isfinite(weights).all()
    assert per_step_ms < 250.0


def test_non_finite_state_disables_reads_writes_and_hints():
    layer = NeuralMemoryLayer(
        ContextEmbedder(),
        None,
        _config(min_warmup_steps=0),
        episode_provider=lambda limit: [
            ("ep1", np.ones(8, dtype=np.float32), "stored episode")
        ],
    )
    assert layer._neural._memory is not None
    layer._neural._memory.net.weights.flat[0] = np.nan

    layer.observe(MemoryObservation("user", "question", "s1"))
    layer.observe(MemoryObservation("assistant", "answer", "s1"))

    assert layer.get_stats()["healthy"] is False
    assert layer.last_surprise() is None
    assert layer.contribute_to_prompt(RecallQuery(query="question")) is None
