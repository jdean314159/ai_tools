from __future__ import annotations

import numpy as np

from engram.neural.neural_memory import NeuralMemory, NeuralMemoryConfig


def test_fresh_initialization_is_seeded_without_mutating_global_rng():
    np.random.seed(7)
    expected_next = np.random.random()
    np.random.seed(7)

    first = NeuralMemory(config=NeuralMemoryConfig(initialization_seed=123, verbose=False))
    observed_next = np.random.random()
    second = NeuralMemory(config=NeuralMemoryConfig(initialization_seed=123, verbose=False))

    assert observed_next == expected_next
    np.testing.assert_array_equal(
        first._memory.net.weights,
        second._memory.net.weights,
    )


def test_neural_memory_step_and_read_use_stable_numpy_defaults():
    np.random.seed(42)
    memory = NeuralMemory(
        config=NeuralMemoryConfig(
            key_dim=64,
            value_dim=16,
            hidden_dim=32,
            lr=0.003,
            grad_clip_norm=1.0,
            device="cpu",
        )
    )
    key = np.ones(64, dtype=np.float32) / np.sqrt(64)
    value = np.linspace(-0.2, 0.2, 16, dtype=np.float32)

    first = memory.step(key, value)
    for _ in range(30):
        memory.step(key, value)
    final = memory.step(key, value)
    recalled = memory.read(key)

    assert memory._memory is not None
    assert memory._memory.B.use_torch is False
    assert recalled.shape == (16,)
    assert np.linalg.norm(recalled) > 0.0
    assert final["surprise"] < first["surprise"]
    assert np.isfinite(recalled).all()
    assert np.isfinite(memory._memory.B.to_numpy(memory._memory.net.p_matrix_old)).all()


def test_neural_memory_state_round_trips(tmp_path):
    np.random.seed(7)
    config = NeuralMemoryConfig(
        key_dim=8,
        value_dim=4,
        hidden_dim=8,
        lr=0.003,
        grad_clip_norm=1.0,
        device="cpu",
    )
    key = np.arange(8, dtype=np.float32) / 8.0
    value = np.array([0.25, -0.5, 0.75, 0.1], dtype=np.float32)
    memory = NeuralMemory(project_dir=tmp_path, config=config)

    for _ in range(12):
        memory.step(key, value)
    expected = memory.read(key)
    memory.save()

    restored = NeuralMemory.load(tmp_path, config=config)

    np.testing.assert_allclose(restored.read(key), expected, atol=1e-6)
    assert restored.get_stats()["total_steps"] == 12
