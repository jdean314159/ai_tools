"""Tests for ProjectMemory.end_session() and configure_synthesis_hook().

Verifies:
  1. end_session() with no hook returns sensible defaults.
  2. Hook below episode threshold does not trigger.
  3. Hook above threshold calls approval_callback.
  4. Approval denied → synthesis_deferred=True.
  5. Approval granted → synthesis_approved=True.
  6. Episode counter resets after end_session() regardless of outcome.
  7. SynthesisHookConfig defaults are correct.

Note: _session_episode_count is incremented only by store_episode() which
runs via async event bus. Tests set it directly to avoid timing dependency.
"""

from __future__ import annotations

from .runner import test_group
from .mocks import TempDir, MockEngine, unique_session


def _make_pm(d):
    from engram.project_memory import ProjectMemory
    return ProjectMemory(
        project_id="hook_test",
        project_type="general_assistant",
        base_dir=d,
        llm_engine=MockEngine(),
        session_id=unique_session(),
    )


# ── SynthesisHookConfig defaults ──────────────────────────────────────────────

@test_group("End Session Hook")
def test_hook_config_defaults():
    """SynthesisHookConfig has expected default values."""
    from engram.project_memory import SynthesisHookConfig
    cfg = SynthesisHookConfig()
    assert cfg.enabled is False
    assert cfg.episode_threshold == 20
    assert cfg.approval_callback is None
    assert cfg.window_size == 50
    assert cfg.days_back == 30
    assert cfg.min_support == 3
    assert cfg.min_confidence == 0.60


# ── end_session with no hook ──────────────────────────────────────────────────

@test_group("End Session Hook")
def test_end_session_no_hook_returns_base_dict():
    """end_session() without a hook returns correct dict shape."""
    with TempDir() as d:
        pm = _make_pm(d)
        pm._session_episode_count = 5
        result = pm.end_session()
        assert isinstance(result, dict)
        assert "episodes_this_session" in result
        assert result["synthesis_triggered"] is False
        assert result["synthesis_approved"] is False
        assert result["synthesis_deferred"] is False
        assert result["synthesis_result"] is None


@test_group("End Session Hook")
def test_end_session_no_hook_resets_counter():
    """Episode counter resets to 0 after end_session() with no hook."""
    with TempDir() as d:
        pm = _make_pm(d)
        pm._session_episode_count = 5
        pm.end_session()
        assert pm._session_episode_count == 0


# ── Hook below threshold ──────────────────────────────────────────────────────

@test_group("End Session Hook")
def test_hook_below_threshold_does_not_trigger():
    """Hook with threshold=10 does not trigger with only 3 episodes."""
    from engram.project_memory import SynthesisHookConfig
    with TempDir() as d:
        pm = _make_pm(d)
        pm.configure_synthesis_hook(SynthesisHookConfig(
            enabled=True,
            episode_threshold=10,
            approval_callback=lambda _: True,
        ))
        pm._session_episode_count = 3
        result = pm.end_session()
        assert result["synthesis_triggered"] is False


# ── Hook at/above threshold ───────────────────────────────────────────────────

@test_group("End Session Hook")
def test_hook_above_threshold_calls_callback():
    """Hook fires and calls approval_callback when threshold met."""
    from engram.project_memory import SynthesisHookConfig

    callback_called = {"n": 0}

    def _deny(prompt_text):
        callback_called["n"] += 1
        assert isinstance(prompt_text, str) and len(prompt_text) > 0
        return False

    with TempDir() as d:
        pm = _make_pm(d)
        pm.configure_synthesis_hook(SynthesisHookConfig(
            enabled=True,
            episode_threshold=2,
            approval_callback=_deny,
        ))
        pm._session_episode_count = 3
        result = pm.end_session()

    assert callback_called["n"] == 1
    assert result["synthesis_triggered"] is True


@test_group("End Session Hook")
def test_hook_denial_sets_deferred():
    """Callback returning False → synthesis_deferred=True, approved=False."""
    from engram.project_memory import SynthesisHookConfig
    with TempDir() as d:
        pm = _make_pm(d)
        pm.configure_synthesis_hook(SynthesisHookConfig(
            enabled=True,
            episode_threshold=2,
            approval_callback=lambda _: False,
        ))
        pm._session_episode_count = 3
        result = pm.end_session()
        assert result["synthesis_deferred"] is True
        assert result["synthesis_approved"] is False


@test_group("End Session Hook")
def test_hook_approval_sets_approved():
    """Callback returning True → synthesis_approved=True."""
    from engram.project_memory import SynthesisHookConfig
    with TempDir() as d:
        pm = _make_pm(d)
        pm.configure_synthesis_hook(SynthesisHookConfig(
            enabled=True,
            episode_threshold=2,
            approval_callback=lambda _: True,
        ))
        pm._session_episode_count = 3
        result = pm.end_session()
        assert result["synthesis_approved"] is True
        assert result["synthesis_deferred"] is False
        # Wait for background thread
        t = getattr(pm, "_synthesis_background_thread", None)
        if t is not None:
            t.join(timeout=10.0)


@test_group("End Session Hook")
def test_episode_counter_resets_after_denial():
    """Counter resets to 0 even when synthesis is denied."""
    from engram.project_memory import SynthesisHookConfig
    with TempDir() as d:
        pm = _make_pm(d)
        pm.configure_synthesis_hook(SynthesisHookConfig(
            enabled=True, episode_threshold=2,
            approval_callback=lambda _: False,
        ))
        pm._session_episode_count = 3
        pm.end_session()
        assert pm._session_episode_count == 0


@test_group("End Session Hook")
def test_episode_counter_resets_after_approval():
    """Counter resets to 0 when synthesis is approved."""
    from engram.project_memory import SynthesisHookConfig
    with TempDir() as d:
        pm = _make_pm(d)
        pm.configure_synthesis_hook(SynthesisHookConfig(
            enabled=True, episode_threshold=2,
            approval_callback=lambda _: True,
        ))
        pm._session_episode_count = 3
        pm.end_session()
        assert pm._session_episode_count == 0
