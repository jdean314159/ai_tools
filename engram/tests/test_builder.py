"""
Unit tests for engram.prompting.builder.

Covers:
- safe_text / safe_score extraction from various item shapes
- count_text_tokens: default word-count and custom counter
- normalize_retrieval_result: ContextResult, dict, arbitrary objects
- format_items: numbering, limit, empty input
- render_sections / _parts_from_prompt: round-trip
- build_prompt_from_context: basic assembly, budget enforcement, compression
- build_prompt_trace_from_result: section and evidence population
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from engram.prompting.builder import (
    _parts_from_prompt,
    build_prompt_from_context,
    build_prompt_trace_from_result,
    count_items_tokens,
    count_text_tokens,
    format_items,
    normalize_retrieval_result,
    render_sections,
    safe_score,
    safe_text,
)
from engram.retrieval.context import ContextResult


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@dataclass
class FakeItem:
    text: str
    score: float | None = None


def word_counter(text: str) -> int:
    """Deterministic token counter: one token per word."""
    return len(text.split()) if text.strip() else 0


# ---------------------------------------------------------------------------
# safe_text
# ---------------------------------------------------------------------------

class TestSafeText:
    def test_dataclass_with_text_attr(self):
        assert safe_text(FakeItem(text="hello")) == "hello"

    def test_dict_with_text_key(self):
        assert safe_text({"text": "world"}) == "world"

    def test_dict_content_key(self):
        assert safe_text({"content": "from content"}) == "from content"

    def test_plain_string_fallback(self):
        assert safe_text("raw string") == "raw string"

    def test_int_fallback(self):
        assert safe_text(42) == "42"

    def test_empty_attr_falls_through_to_str(self):
        # text attr exists but is blank — should fall through to str()
        item = FakeItem(text="   ")
        result = safe_text(item)
        # blank attr not accepted; falls back to str(item)
        assert result  # non-empty

    def test_dict_prefers_text_over_content(self):
        assert safe_text({"text": "primary", "content": "secondary"}) == "primary"


# ---------------------------------------------------------------------------
# safe_score
# ---------------------------------------------------------------------------

class TestSafeScore:
    def test_from_attr(self):
        assert safe_score(FakeItem(text="x", score=0.9)) == pytest.approx(0.9)

    def test_from_dict(self):
        assert safe_score({"score": 0.5}) == pytest.approx(0.5)

    def test_similarity_key(self):
        assert safe_score({"similarity": 0.7}) == pytest.approx(0.7)

    def test_missing_returns_none(self):
        assert safe_score({"text": "no score here"}) is None

    def test_non_numeric_returns_none(self):
        assert safe_score({"score": "high"}) is None


# ---------------------------------------------------------------------------
# count_text_tokens
# ---------------------------------------------------------------------------

class TestCountTextTokens:
    def test_empty_string(self):
        assert count_text_tokens("") == 0

    def test_whitespace_only(self):
        assert count_text_tokens("   ") == 0

    def test_word_count_default(self):
        assert count_text_tokens("one two three") == 3

    def test_custom_counter(self):
        assert count_text_tokens("hello world", token_counter=word_counter) == 2

    def test_custom_counter_exception_falls_back(self):
        def bad_counter(t: str) -> int:
            raise RuntimeError("broken")
        # Should not raise; falls back to word split
        result = count_text_tokens("one two", token_counter=bad_counter)
        assert result >= 1


# ---------------------------------------------------------------------------
# normalize_retrieval_result
# ---------------------------------------------------------------------------

class TestNormalizeRetrievalResult:
    def test_context_result_passthrough(self):
        ctx = ContextResult(
            working=[FakeItem("w1")],
            episodic=[FakeItem("e1"), FakeItem("e2")],
        )
        result = normalize_retrieval_result(ctx, token_counter=word_counter)
        assert len(result.working) == 1
        assert len(result.episodic) == 2
        assert result.working_tokens > 0
        assert result.episodic_tokens > 0

    def test_dict_input(self):
        raw = {
            "working": [FakeItem("working memory hit")],
            "episodic": [],
            "semantic": [FakeItem("semantic fact")],
            "cold": [],
        }
        result = normalize_retrieval_result(raw, token_counter=word_counter)
        assert len(result.working) == 1
        assert len(result.semantic) == 1
        assert result.cold == []

    def test_none_input(self):
        result = normalize_retrieval_result(None)
        assert result.working == []
        assert result.memory_tokens() == 0

    def test_memory_tokens_sums_all_layers(self):
        ctx = ContextResult(working_tokens=10, episodic_tokens=20, semantic_tokens=5, cold_tokens=3)
        assert ctx.memory_tokens() == 38

    def test_single_item_coerced_to_list(self):
        """A scalar item (not a list) should be coerced to [item]."""
        raw = {"working": FakeItem("solo item"), "episodic": [], "semantic": [], "cold": []}
        result = normalize_retrieval_result(raw)
        assert len(result.working) == 1


# ---------------------------------------------------------------------------
# format_items
# ---------------------------------------------------------------------------

class TestFormatItems:
    def test_empty(self):
        assert format_items([]) == ""

    def test_single(self):
        out = format_items([FakeItem("apple")])
        assert "1. apple" in out

    def test_multiple_numbered(self):
        items = [FakeItem(f"item{i}") for i in range(3)]
        out = format_items(items)
        assert "1. item0" in out
        assert "3. item2" in out

    def test_limit_truncates(self):
        items = [FakeItem(f"x{i}") for i in range(20)]
        out = format_items(items, limit=5)
        assert "15 more" in out
        assert "6." not in out

    def test_dict_items(self):
        out = format_items([{"text": "dict item"}])
        assert "dict item" in out


# ---------------------------------------------------------------------------
# render_sections / _parts_from_prompt round-trip
# ---------------------------------------------------------------------------

class TestRenderAndParse:
    def test_round_trip(self):
        parts = [
            ("system", "System", "You are helpful."),
            ("working", "Working", "1. recent fact"),
            ("user", "User", "Hello?"),
        ]
        rendered = render_sections(parts)
        recovered = _parts_from_prompt(rendered)
        titles = [t for _, t, _ in recovered]
        assert "System" in titles
        assert "Working" in titles
        assert "User" in titles

    def test_empty_text_sections_skipped(self):
        parts = [("system", "System", ""), ("user", "User", "Hi")]
        rendered = render_sections(parts)
        assert "## System" not in rendered
        assert "## User" in rendered

    def test_empty_prompt(self):
        assert _parts_from_prompt("") == []


# ---------------------------------------------------------------------------
# build_prompt_from_context
# ---------------------------------------------------------------------------

class TestBuildPromptFromContext:
    def _ctx(self, working=None, episodic=None) -> ContextResult:
        return ContextResult(
            working=working or [],
            episodic=episodic or [],
        )

    def test_basic_assembly(self):
        ctx = self._ctx(working=[FakeItem("remember this")])
        result = build_prompt_from_context(
            user_message="test",
            context=ctx,
            token_counter=word_counter,
        )
        assert "## User" in result["prompt"]
        assert "## Working" in result["prompt"]
        assert result["compressed"] is False

    def test_system_prompt_included(self):
        result = build_prompt_from_context(
            user_message="hi",
            system_prompt="Be concise.",
            token_counter=word_counter,
        )
        assert "## System" in result["prompt"]
        assert "Be concise." in result["prompt"]

    def test_budget_triggers_compression(self):
        # Make memory that will exceed a tiny budget
        big_memory = [FakeItem("word " * 50) for _ in range(5)]
        ctx = self._ctx(working=big_memory)
        result = build_prompt_from_context(
            user_message="short",
            context=ctx,
            total_prompt_tokens=10,   # tiny budget
            reserve_output_tokens=0,
            token_counter=word_counter,
        )
        assert result["compressed"] is True

    def test_user_message_always_included(self):
        """Even under extreme budget pressure, the user message must survive."""
        ctx = self._ctx(working=[FakeItem("word " * 100)])
        result = build_prompt_from_context(
            user_message="the question",
            context=ctx,
            total_prompt_tokens=5,
            reserve_output_tokens=0,
            token_counter=word_counter,
        )
        assert "the question" in result["prompt"]

    def test_empty_context(self):
        result = build_prompt_from_context(user_message="hello", token_counter=word_counter)
        assert "hello" in result["prompt"]
        assert result["memory_tokens"] == 0

    def test_return_trace_flag(self):
        result = build_prompt_from_context(
            user_message="trace test",
            return_trace=True,
            token_counter=word_counter,
        )
        assert "trace" in result
        assert result["trace"] is not None

    def test_no_trace_by_default(self):
        result = build_prompt_from_context(user_message="no trace", token_counter=word_counter)
        assert "trace" not in result


# ---------------------------------------------------------------------------
# build_prompt_trace_from_result
# ---------------------------------------------------------------------------

class TestBuildPromptTraceFromResult:
    def _make_result(self, prompt: str = "## User\nhello", ctx: Any = None) -> dict:
        return {
            "prompt": prompt,
            "context": ctx,
            "prompt_tokens": None,
            "memory_tokens": None,
            "compressed": False,
        }

    def test_sections_populated(self):
        result = self._make_result()
        trace = build_prompt_trace_from_result(
            user_message="hello",
            result=result,
            token_counter=word_counter,
        )
        assert any(s.title == "User" for s in trace.sections)

    def test_evidence_from_context(self):
        ctx = ContextResult(
            working=[FakeItem("working hit")],
            episodic=[FakeItem("episodic hit")],
        )
        prompt = "## Working\n1. working hit\n\n## Episodic\n1. episodic hit\n\n## User\nhello"
        result = self._make_result(prompt=prompt, ctx=ctx)
        trace = build_prompt_trace_from_result(
            user_message="hello",
            result=result,
            token_counter=word_counter,
        )
        sources = {e.source for e in trace.evidence}
        assert "working" in sources
        assert "episodic" in sources

    def test_token_accounting_present(self):
        result = self._make_result()
        trace = build_prompt_trace_from_result(
            user_message="hello",
            result=result,
            max_prompt_tokens=1000,
            token_counter=word_counter,
        )
        assert trace.token_accounting is not None
        assert trace.token_accounting.target_tokens > 0

    def test_flags_include_query(self):
        result = self._make_result()
        trace = build_prompt_trace_from_result(
            user_message="hello",
            result=result,
            query="explicit query",
        )
        assert trace.flags.get("query") == "explicit query"

    def test_to_dict_serializable(self):
        result = self._make_result()
        trace = build_prompt_trace_from_result(
            user_message="hello",
            result=result,
            token_counter=word_counter,
        )
        d = trace.to_dict()
        assert isinstance(d, dict)
        assert "sections" in d
        assert "evidence" in d
        assert "token_accounting" in d
