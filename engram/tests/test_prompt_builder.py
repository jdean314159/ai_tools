"""Unit tests for engram.prompt.builder.

Tests focus on hierarchical_compress_text (a pure function) and
_get_helper_map (the lazy ProjectType helper factory).
build_prompt_core and build_prompt_trace_core are integration-tested
by the harness test suite and are not duplicated here.
"""
from __future__ import annotations

import pytest
from engram.prompt.builder import _get_helper_map, hierarchical_compress_text


# ---------------------------------------------------------------------------
# Simple token counter used throughout
# ---------------------------------------------------------------------------

def char_count(text: str) -> int:
    return len(text)


# ---------------------------------------------------------------------------
# hierarchical_compress_text — fits within budget
# ---------------------------------------------------------------------------

def test_hct_fits_in_budget_unchanged():
    sections = {"working": "hello", "episodic": "", "semantic": "a fact", "cold": ""}
    result = hierarchical_compress_text(sections, "", 10_000, char_count)
    assert "hello" in result
    assert "a fact" in result


def test_hct_empty_sections_returns_empty():
    result = hierarchical_compress_text({}, "", 1000, char_count)
    assert result == ""


def test_hct_all_empty_sections_returns_empty():
    sections = {"working": "", "episodic": "", "semantic": "", "cold": ""}
    result = hierarchical_compress_text(sections, "", 1000, char_count)
    assert result.strip() == ""


def test_hct_formats_sections_with_labels():
    sections = {"working": "w", "semantic": "s", "episodic": "", "cold": ""}
    result = hierarchical_compress_text(sections, "", 10_000, char_count)
    assert "[WORKING]" in result
    assert "[SEMANTIC]" in result


def test_hct_neural_hint_included_when_budget_allows():
    sections = {"semantic": "fact"}
    result = hierarchical_compress_text(sections, "neural hint here", 10_000, char_count)
    assert "neural hint here" in result


# ---------------------------------------------------------------------------
# Phase 1: drops cold storage first
# ---------------------------------------------------------------------------

def test_hct_drops_cold_before_other_layers():
    # cold is large; budget is tight
    cold = "c" * 300
    semantic = "s" * 20
    sections = {"working": "", "episodic": "", "semantic": semantic, "cold": cold}

    # budget that fits semantic but not cold
    budget = char_count(f"[SEMANTIC]\n{semantic}") + 30
    result = hierarchical_compress_text(sections, "", budget, char_count)

    assert "[COLD]" not in result
    assert semantic in result


# ---------------------------------------------------------------------------
# Phase 1b: drops neural hint before episodic
# ---------------------------------------------------------------------------

def test_hct_drops_neural_hint_before_episodic():
    episodic = "e" * 50
    hint = "h" * 100
    sections = {"working": "", "episodic": episodic, "semantic": "", "cold": ""}
    # budget that fits episodic but not episodic + hint
    budget = char_count(f"[EPISODIC]\n{episodic}") + 20
    result = hierarchical_compress_text(sections, hint, budget, char_count)
    assert "h" * 100 not in result      # hint dropped
    assert episodic in result           # episodic kept


# ---------------------------------------------------------------------------
# Phase 4: semantic is non-evictable under extreme pressure
# ---------------------------------------------------------------------------

def test_hct_retains_semantic_under_extreme_pressure():
    semantic = "critical fact"
    sections = {
        "working": "w" * 500,
        "episodic": "e" * 500,
        "semantic": semantic,
        "cold": "c" * 500,
    }
    # budget too small for anything except semantic
    result = hierarchical_compress_text(sections, "hint" * 50, 30, char_count)
    assert semantic in result


# ---------------------------------------------------------------------------
# _get_helper_map — sanity checks (lazy-loaded, avoid heavy imports)
# ---------------------------------------------------------------------------

def test_get_helper_map_returns_dict():
    result = _get_helper_map()
    assert isinstance(result, dict)


def test_get_helper_map_language_tutor_has_helper():
    helper_map = _get_helper_map()
    from engram.memory.types import ProjectType
    tutor_helper = helper_map.get(ProjectType.LANGUAGE_TUTOR)
    assert tutor_helper is not None


def test_get_helper_map_values_are_callable():
    helper_map = _get_helper_map()
    for key, value in helper_map.items():
        assert callable(value), f"Helper for {key} is not callable"
