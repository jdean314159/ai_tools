"""Tests for synthesis origin rendering in the console renderer.

Verifies that sections with origin='synthesis' render with [RUL] prefix
and that the origin refactor didn't leave legacy '[system]'/'[user]' prefixes.
"""

from __future__ import annotations

from llm_inspector.augmenters import BaselineAugmenter
from llm_inspector.inspectors import ContextInspector
from llm_inspector.inspectors.context_inspector import NamedTrace, ComparisonReport
from llm_inspector.core.trace import ContextResult, Trace, TokenAccounting, RunMetrics
from llm_inspector.core.types import Section, Turn
from llm_inspector.core.types import Section
from llm_inspector.renderers import render_comparison
from llm_inspector.renderers.origins import console_prefix


# ── console_prefix unit tests ─────────────────────────────────────────────────

def test_synthesis_prefix_is_rul():
    assert console_prefix("synthesis") == "[RUL]"


def test_system_prefix_is_sys():
    """Regression: refactor must not have reverted [SYS]."""
    assert console_prefix("system") == "[SYS]"


def test_user_prefix_is_usr():
    """Regression: refactor must not have reverted [USR]."""
    assert console_prefix("user") == "[USR]"


# ── Integration with render_comparison ────────────────────────────────────────

def _baseline_report():
    a = BaselineAugmenter(system_prompt="You are helpful.", _name="test_aug")
    return ContextInspector([a]).run("hello")


def test_render_uses_sys_not_legacy_system():
    out = render_comparison(_baseline_report())
    assert "[SYS]" in out
    assert "[system]" not in out


def test_render_uses_usr_not_legacy_user():
    out = render_comparison(_baseline_report())
    assert "[USR]" in out
    assert "[user]" not in out


def _make_synthesis_report():
    """Build a ComparisonReport with a synthesis section."""
    section = Section(
        origin="synthesis",
        title="Procedural Rules",
        text="When X, do Y.",
        tokens=5,
    )
    accounting = TokenAccounting(target_tokens=2048, total_tokens=10)
    ctx = ContextResult(sections=[section], token_accounting=accounting)
    turn = Turn(role="user", text="test", session_id="s1")
    trace = Trace(turn=turn, context=ctx, metrics=RunMetrics())
    named = NamedTrace(name="synth_aug", trace=trace)
    return ComparisonReport(query="test", traces=[named])


def test_synthesis_section_renders_with_rul():
    """A trace section with origin='synthesis' must use [RUL] prefix."""
    out = render_comparison(_make_synthesis_report())
    assert "[RUL]" in out, f"Expected [RUL] in:\n{out}"


def test_synthesis_section_title_present():
    """The section title 'Procedural Rules' must appear in the output."""
    out = render_comparison(_make_synthesis_report())
    assert "Procedural Rules" in out
