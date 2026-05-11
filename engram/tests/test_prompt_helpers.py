"""Unit tests for engram.prompt.helpers.

These functions are pure (no ProjectMemory, no I/O) so tests are fast
and self-contained.
"""
from __future__ import annotations

import pytest
from engram.prompt.helpers import (
    _MEMORY_WRAPPER_BEGIN,
    _MEMORY_WRAPPER_END,
    _MEMORY_WRAPPER_PREAMBLE,
    _canonical_sentence_for_prompt,
    _canonical_subject_for_prompt,
    _canonical_value_for_prompt,
    _prompt_friendly_episodic_text,
    _prompt_friendly_semantic_row,
    assemble_prompt,
    truncate_to_tokens,
    wrap_memory_block,
)


# ---------------------------------------------------------------------------
# wrap_memory_block
# ---------------------------------------------------------------------------

def test_wrap_empty_returns_empty():
    assert wrap_memory_block("") == ""
    assert wrap_memory_block("   ") == ""


def test_wrap_non_empty_contains_markers():
    result = wrap_memory_block("some memory content")
    assert _MEMORY_WRAPPER_PREAMBLE in result
    assert _MEMORY_WRAPPER_BEGIN in result
    assert _MEMORY_WRAPPER_END in result
    assert "some memory content" in result


def test_wrap_strips_content_whitespace():
    result = wrap_memory_block("  padded  ")
    assert "padded" in result
    assert "  padded  " not in result


# ---------------------------------------------------------------------------
# assemble_prompt
# ---------------------------------------------------------------------------

def test_assemble_all_components():
    result = assemble_prompt("SYSTEM", "MEMORY", "hello")
    assert "SYSTEM" in result
    assert "MEMORY" in result
    assert "User: hello" in result
    assert "Assistant:" in result


def test_assemble_no_memory_omits_separator():
    with_memory = assemble_prompt("SYS", "MEM", "q")
    without_memory = assemble_prompt("SYS", "", "q")
    # without_memory should have fewer double-newlines
    assert without_memory.count("\n\n") < with_memory.count("\n\n")
    assert "User: q" in without_memory


def test_assemble_no_system():
    result = assemble_prompt("", "", "question")
    assert "User: question" in result
    assert result.startswith("User:")


def test_assemble_user_message_always_present():
    result = assemble_prompt("", "", "my question")
    assert "my question" in result


# ---------------------------------------------------------------------------
# truncate_to_tokens
# ---------------------------------------------------------------------------

def word_count(text: str) -> int:
    return len(text.split()) if text.strip() else 0


def char_count(text: str) -> int:
    return len(text)


def test_truncate_within_budget_unchanged():
    text = "hello world"
    assert truncate_to_tokens(text, 100, char_count) == text


def test_truncate_over_budget():
    text = "a" * 100
    result = truncate_to_tokens(text, 50, char_count)
    assert len(result) <= 50


def test_truncate_zero_budget_returns_empty():
    assert truncate_to_tokens("anything", 0, char_count) == ""


def test_truncate_preserves_prefix():
    text = "first second third fourth fifth"
    result = truncate_to_tokens(text, 11, char_count)
    assert text.startswith(result)


def test_truncate_exact_fit_unchanged():
    text = "exactly ten"
    assert truncate_to_tokens(text, len(text), char_count) == text


# ---------------------------------------------------------------------------
# _canonical_* helpers
# ---------------------------------------------------------------------------

def test_canonical_subject_capitalises():
    assert _canonical_subject_for_prompt("hello world") == "Hello world"


def test_canonical_subject_strips_punctuation():
    assert _canonical_subject_for_prompt("hello.") == "Hello"


def test_canonical_subject_empty():
    assert _canonical_subject_for_prompt("") == ""


def test_canonical_value_strips_whitespace_and_punctuation():
    assert _canonical_value_for_prompt("  python. ") == "python"


def test_canonical_value_none():
    assert _canonical_value_for_prompt(None) == ""


def test_canonical_sentence_adds_period():
    result = _canonical_sentence_for_prompt("hello world")
    assert result.endswith(".")


def test_canonical_sentence_capitalises():
    assert _canonical_sentence_for_prompt("lower") == "Lower."


def test_canonical_sentence_empty():
    assert _canonical_sentence_for_prompt("") == ""


# ---------------------------------------------------------------------------
# _prompt_friendly_episodic_text
# ---------------------------------------------------------------------------

def test_episodic_empty_returns_empty():
    assert _prompt_friendly_episodic_text("") == ""
    assert _prompt_friendly_episodic_text("   ") == ""


def test_episodic_transient_note_filtered():
    assert _prompt_friendly_episodic_text("Transient note: ignore this") == ""


def test_episodic_plain_text_unchanged():
    text = "I went to the store yesterday."
    assert _prompt_friendly_episodic_text(text) == text


def test_episodic_correction_pattern_normalised():
    raw = "Correction: for pandas, use pandas 2.0 instead of pandas 1.5."
    result = _prompt_friendly_episodic_text(raw)
    assert "pandas" in result.lower()
    assert "2.0" in result


def test_episodic_schedule_update_normalised():
    raw = "Update: the meeting has moved to Thursday."
    result = _prompt_friendly_episodic_text(raw)
    assert "Thursday" in result
    # Should NOT contain the raw "has moved to" phrasing
    assert "has moved to" not in result


def test_episodic_keep_in_not_in_normalised():
    raw = "Preference: keep config in /etc, not in ~/."
    result = _prompt_friendly_episodic_text(raw)
    assert "/etc" in result


# ---------------------------------------------------------------------------
# _prompt_friendly_semantic_row
# ---------------------------------------------------------------------------

def test_semantic_row_preference():
    row = {"type": "preference", "category": "language", "value": "Python"}
    result = _prompt_friendly_semantic_row(row)
    assert "language" in result
    assert "Python" in result


def test_semantic_row_event_uses_summary():
    row = {"type": "event", "summary": "Team standup at 9am"}
    assert _prompt_friendly_semantic_row(row) == "Team standup at 9am"


def test_semantic_row_graph_context():
    row = {"type": "graph_context", "content": "Node: Alice, role: PM"}
    assert "Alice" in _prompt_friendly_semantic_row(row)


def test_semantic_row_default_fact():
    row = {"type": "fact", "content": "The sky is blue."}
    assert "The sky is blue." in _prompt_friendly_semantic_row(row)


def test_semantic_row_empty_returns_empty():
    assert _prompt_friendly_semantic_row({}) == ""
