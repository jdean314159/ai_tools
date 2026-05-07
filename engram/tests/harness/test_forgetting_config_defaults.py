"""Tests for ForgettingConfig defaults and ForgettingPolicy behaviour.

The defaults were tuned last thread:
  min_age_days:           7  → 30
  recency_half_life_days: 30 → 60

Tests verify:
  1. Dataclass defaults match the tuned values.
  2. Weights sum to 1.0.
  3. Other defaults are stable.
  4. Custom config overrides defaults.
  5. should_auto_run() triggers at auto_trigger_interval.
  6. min_episodes guard skips archival when count is too low.
  7. score_episode() respects min_age_days (young → not archived).
"""

from __future__ import annotations

import time
from pathlib import Path

from .runner import test_group
from .mocks import TempDir


# ── Dataclass defaults ────────────────────────────────────────────────────────

@test_group("Forgetting Config Defaults")
def test_min_age_days_is_30():
    """min_age_days default must be 30 (tuned from 7)."""
    from engram.memory.forgetting import ForgettingConfig
    assert ForgettingConfig().min_age_days == 30.0


@test_group("Forgetting Config Defaults")
def test_recency_half_life_is_60():
    """recency_half_life_days default must be 60 (tuned from 30)."""
    from engram.memory.forgetting import ForgettingConfig
    assert ForgettingConfig().recency_half_life_days == 60.0


@test_group("Forgetting Config Defaults")
def test_weights_sum_to_one():
    """Retention score weights must sum to 1.0."""
    from engram.memory.forgetting import ForgettingConfig
    cfg = ForgettingConfig()
    total = (cfg.weight_recency + cfg.weight_importance
             + cfg.weight_access + cfg.weight_surprise)
    assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, expected 1.0"


@test_group("Forgetting Config Defaults")
def test_retention_threshold_default():
    """retention_threshold default is 0.3."""
    from engram.memory.forgetting import ForgettingConfig
    assert ForgettingConfig().retention_threshold == 0.3


@test_group("Forgetting Config Defaults")
def test_enabled_default_is_true():
    from engram.memory.forgetting import ForgettingConfig
    assert ForgettingConfig().enabled is True


@test_group("Forgetting Config Defaults")
def test_min_episodes_before_archival_default():
    from engram.memory.forgetting import ForgettingConfig
    assert ForgettingConfig().min_episodes_before_archival == 50


@test_group("Forgetting Config Defaults")
def test_custom_config_overrides_defaults():
    from engram.memory.forgetting import ForgettingConfig
    cfg = ForgettingConfig(min_age_days=5.0, recency_half_life_days=14.0, enabled=False)
    assert cfg.min_age_days == 5.0
    assert cfg.recency_half_life_days == 14.0
    assert cfg.enabled is False


# ── ForgettingPolicy unit behaviour ──────────────────────────────────────────

@test_group("Forgetting Config Defaults")
def test_should_auto_run_triggers_at_interval():
    """should_auto_run() returns True after auto_trigger_interval new episodes."""
    from engram.memory.forgetting import ForgettingPolicy, ForgettingConfig
    with TempDir() as d:
        cfg = ForgettingConfig(auto_trigger_interval=3)
        policy = ForgettingPolicy(access_db_path=d / "access.db", config=cfg)
        assert policy.should_auto_run() is False
        policy.record_new_episode()
        policy.record_new_episode()
        assert policy.should_auto_run() is False
        policy.record_new_episode()
        assert policy.should_auto_run() is True


@test_group("Forgetting Config Defaults")
def test_should_auto_run_false_when_disabled():
    """should_auto_run() is always False when config.enabled=False."""
    from engram.memory.forgetting import ForgettingPolicy, ForgettingConfig
    with TempDir() as d:
        cfg = ForgettingConfig(auto_trigger_interval=1, enabled=False)
        policy = ForgettingPolicy(access_db_path=d / "access.db", config=cfg)
        policy.record_new_episode()
        assert policy.should_auto_run() is False


@test_group("Forgetting Config Defaults")
def test_min_episodes_guard_skips_archival():
    """run() returns 'skipped' when episodic count < min_episodes_before_archival."""
    from engram.memory.forgetting import ForgettingPolicy, ForgettingConfig
    from unittest.mock import MagicMock

    with TempDir() as d:
        cfg = ForgettingConfig(min_episodes_before_archival=50)
        policy = ForgettingPolicy(access_db_path=d / "access.db", config=cfg)

        # Mock episodic_memory returning only 5 episodes
        episodic = MagicMock()
        episodic.get_stats.return_value = {"total_episodes": 5}
        cold = MagicMock()

        result = policy.run(episodic, cold, project_id="test_proj")
        assert result.get("status") == "skipped", (
            f"Expected status='skipped', got {result}"
        )


@test_group("Forgetting Config Defaults")
def test_score_episode_young_has_high_recency():
    """A brand-new episode scores high on recency (age ≈ 0 days)."""
    from engram.memory.forgetting import ForgettingPolicy, ForgettingConfig
    with TempDir() as d:
        cfg = ForgettingConfig(recency_half_life_days=60.0)
        policy = ForgettingPolicy(access_db_path=d / "access.db", config=cfg)
        score = policy.score_episode(
            episode_id="ep_new",
            timestamp=time.time(),   # age ≈ 0
            importance=0.5,
            access_count=0,
            max_access_count=0,
        )
        # At age 0, recency ≈ 1.0 — total must be well above archive threshold
        assert score.recency > 0.95, f"Expected recency>0.95, got {score.recency}"
        assert score.total >= cfg.retention_threshold, (
            f"Fresh episode scored below retention threshold: {score.total}"
        )


@test_group("Forgetting Config Defaults")
def test_score_episode_old_has_low_recency():
    """An episode 365 days old has significantly decayed recency."""
    from engram.memory.forgetting import ForgettingPolicy, ForgettingConfig
    with TempDir() as d:
        cfg = ForgettingConfig(recency_half_life_days=60.0)
        policy = ForgettingPolicy(access_db_path=d / "access.db", config=cfg)
        old_ts = time.time() - 365 * 86400
        score = policy.score_episode(
            episode_id="ep_old",
            timestamp=old_ts,
            importance=0.0,
            access_count=0,
            max_access_count=0,
        )
        # After ~6 half-lives, recency should be well below 0.05
        assert score.recency < 0.05, f"Expected recency<0.05, got {score.recency}"
