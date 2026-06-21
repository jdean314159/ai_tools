from __future__ import annotations

import numpy as np

from engram.neural.core import ModernSubgroupedRTRL, RTRLConfig


def _internal_state_signal(length: int = 300) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(42)
    inputs = []
    targets = []
    previous_was_zero = False

    for _ in range(length):
        symbol = rng.randint(0, 4)
        vector = np.zeros(4, dtype=np.float32)
        vector[symbol] = 1.0
        inputs.append(vector)
        targets.append([1.0 if symbol == 1 and previous_was_zero else 0.0])
        previous_was_zero = symbol == 0

    return np.asarray(inputs), np.asarray(targets, dtype=np.float32)


def test_numpy_rtrl_learns_deterministic_internal_state_signal():
    np.random.seed(42)
    inputs, targets = _internal_state_signal()
    network = ModernSubgroupedRTRL(
        RTRLConfig(
            num_inputs=4,
            num_outputs=1,
            num_hidden=2,
            time_delay=1,
            epochs=50,
            lr=0.003,
            optimizer="adam",
            grad_clip_norm=1.0,
            gated=True,
            hidden_activation="tanh",
            output_activation="sigmoid",
            categorical_output=False,
            device="cpu",
            verbose=False,
        )
    )

    history = network.train(inputs, targets)

    assert network.B.use_torch is False
    assert history[-1]["avg_error"] < history[0]["avg_error"] * 0.5
    assert history[-1]["accuracy"] >= 90.0
    assert np.isfinite(network.B.to_numpy(network.weights)).all()
