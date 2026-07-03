import numpy as np
import pytest

import integration_tests.eval.candidate_utility_eval as utility_eval
from integration_tests.eval.candidate_utility_eval import (
    _balanced_training,
    _features,
)


def test_embedding_cache_creates_parent_before_checkpoint(tmp_path, monkeypatch):
    class FakeEmbedder:
        def __init__(self, **kwargs):
            del kwargs

        def embed(self, text):
            return type("Result", (), {"embedding": [float(len(text)), 1.0]})()

    monkeypatch.setattr(utility_eval, "OllamaEmbedder", FakeEmbedder)
    path = tmp_path / "nested" / "embeddings.json"

    result = utility_eval._embed_texts(
        [str(index) for index in range(26)],
        cache_path=path,
        model="fake",
        base_url="http://unused",
    )

    assert path.exists()
    assert len(result) == 26


def test_features_use_only_deployable_candidate_signals():
    candidate = {
        "text": "deployment region west",
        "importance": 0.6,
        "recency": 0.4,
        "repetition": 0.125,
    }

    features = _features(
        "which deployment region",
        candidate,
        similarity=0.8,
        rank=2,
        score_spread=0.2,
    )

    assert features.shape == (8,)
    assert features.tolist()[:3] == pytest.approx([0.8, 0.5, 0.2])


def test_balanced_training_is_seeded_and_balances_classes():
    rows = [
        {
            "candidates": [
                {"features": np.ones(8), "label": 1.0},
                {"features": np.zeros(8), "label": 0.0, "hard_negative": True},
                {"features": np.full(8, 2.0), "label": 0.0},
            ]
        }
    ]

    first_data, first_targets = _balanced_training(rows, 7)
    second_data, second_targets = _balanced_training(rows, 7)

    np.testing.assert_array_equal(first_data, second_data)
    np.testing.assert_array_equal(first_targets, second_targets)
    assert first_targets[:, 0].tolist().count(1.0) == 1
    assert first_targets[:, 0].tolist().count(0.0) == 1
    negative = first_data[first_targets[:, 0] == 0.0]
    np.testing.assert_array_equal(negative, np.zeros((1, 8)))
