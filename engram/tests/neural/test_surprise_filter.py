from __future__ import annotations

import pytest

from engram.neural.surprise_filter import (
    SurpriseBaseline,
    SurpriseFilter,
)


class _WorkingEngine:
    supports_logprobs = True

    def generate_with_logprobs(self, text, **kwargs):
        class Result:
            token_count = 4
            mean_logprob = -2.0
            perplexity = 10.0

        return Result()


class _NoLogprobsEngine:
    supports_logprobs = False


def test_high_surprise_passes_and_low_surprise_is_suppressed():
    surprise_filter = SurpriseFilter(
        _WorkingEngine(),
        base_threshold=5.0,
        calibration_required=False,
    )

    assert surprise_filter.should_store("novel", perplexity=10.0) is True
    assert surprise_filter.should_store("familiar", perplexity=2.0) is False
    assert surprise_filter.stats.total_stored == 1
    assert surprise_filter.stats.total_rejected == 1


def test_adaptive_threshold_tracks_recent_calibrated_perplexity():
    surprise_filter = SurpriseFilter(
        _WorkingEngine(),
        base_threshold=10.0,
        momentum=0.9,
        buffer_size=20,
    )
    surprise_filter.baseline = SurpriseBaseline(
        mean=10.0,
        std=10.0,
        percentiles={50: 8.0, 80: 10.0, 90: 12.0, 95: 15.0},
        sample_count=100,
        calibration_date=0.0,
    )
    surprise_filter.is_calibrated = True
    surprise_filter.current_threshold = 10.0

    for _ in range(10):
        surprise_filter.should_store("recently surprising", perplexity=20.0)

    assert surprise_filter.current_threshold == pytest.approx(11.0)


def test_missing_logprobs_uses_conservative_pass_through():
    surprise_filter = SurpriseFilter(_NoLogprobsEngine())

    assert surprise_filter.should_store("keep this") is True
    assert surprise_filter.get_stats()["logprobs_available"] is False
