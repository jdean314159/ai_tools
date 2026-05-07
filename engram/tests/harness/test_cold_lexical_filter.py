"""Tests for the cold storage lexical overlap filter in retrieval.py.

The filter (min_cold_lexical_overlap=0.15) prevents decoy bleed through
the FTS5 fallback path. Tests verify:
  1. Overlap calculation: zero / partial / full matches.
  2. Default threshold is 0.15; threshold is configurable.
  3. Integration: zero-overlap cold candidates excluded from results.
  4. Integration: matching content is not over-filtered.
"""

from __future__ import annotations

from .runner import test_group
from .mocks import TempDir, MockEngine, unique_session


def _make_pm(d):
    from engram.project_memory import ProjectMemory
    return ProjectMemory(
        project_id="lexical_test",
        project_type="general_assistant",
        base_dir=d,
        llm_engine=MockEngine(),
        session_id=unique_session(),
    )


# ── Unit: _lexical_overlap_terms ──────────────────────────────────────────────

@test_group("Cold Lexical Filter")
def test_lexical_overlap_zero_for_unrelated_text():
    """No shared terms → overlap = 0.0."""
    with TempDir() as d:
        pm = _make_pm(d)
        r = pm.retriever
        query_terms = r._tokenize("asyncio event loop")
        overlap = r._lexical_overlap_terms(query_terms, "the quick brown fox")
        assert overlap == 0.0, f"Expected 0.0, got {overlap}"


@test_group("Cold Lexical Filter")
def test_lexical_overlap_full_for_all_terms_present():
    """All query terms in text → overlap = 1.0."""
    with TempDir() as d:
        pm = _make_pm(d)
        r = pm.retriever
        query_terms = r._tokenize("asyncio event loop")
        overlap = r._lexical_overlap_terms(
            query_terms, "asyncio event loop and more words"
        )
        assert overlap == 1.0, f"Expected 1.0, got {overlap}"


@test_group("Cold Lexical Filter")
def test_lexical_overlap_partial():
    """One of two query terms present → overlap ~0.5."""
    with TempDir() as d:
        pm = _make_pm(d)
        r = pm.retriever
        query_terms = r._tokenize("asyncio threading")
        overlap = r._lexical_overlap_terms(
            query_terms, "asyncio handles IO concurrency"
        )
        assert 0.4 <= overlap <= 0.6, f"Expected ~0.5, got {overlap}"


@test_group("Cold Lexical Filter")
def test_lexical_overlap_empty_query_returns_zero():
    """Empty query terms → 0.0 (no ZeroDivisionError)."""
    with TempDir() as d:
        pm = _make_pm(d)
        overlap = pm.retriever._lexical_overlap_terms(set(), "some text")
        assert overlap == 0.0


@test_group("Cold Lexical Filter")
def test_lexical_overlap_empty_text_returns_zero():
    """Empty candidate text → 0.0 (no ZeroDivisionError)."""
    with TempDir() as d:
        pm = _make_pm(d)
        r = pm.retriever
        query_terms = r._tokenize("asyncio event loop")
        assert r._lexical_overlap_terms(query_terms, "") == 0.0


# ── Unit: RetrievalPolicy threshold ───────────────────────────────────────────

@test_group("Cold Lexical Filter")
def test_default_threshold_is_0_15():
    """Default min_cold_lexical_overlap must be 0.15."""
    from engram.memory.retrieval import RetrievalPolicy
    assert RetrievalPolicy().min_cold_lexical_overlap == 0.15


@test_group("Cold Lexical Filter")
def test_threshold_is_configurable():
    """RetrievalPolicy accepts a custom threshold."""
    from engram.memory.retrieval import RetrievalPolicy
    assert RetrievalPolicy(min_cold_lexical_overlap=0.30).min_cold_lexical_overlap == 0.30


# ── Integration ───────────────────────────────────────────────────────────────

@test_group("Cold Lexical Filter")
def test_cold_filter_excludes_zero_overlap_decoys():
    """Cold results must all share at least one query term with the query."""
    with TempDir() as d:
        pm = _make_pm(d)
        pm.add_turn("user", "The capital of France is Paris.")
        pm.add_turn("assistant", "Yes, Paris is the capital of France.")

        ctx = pm.get_context(
            query="asyncio concurrent programming event loop", max_tokens=500
        )
        cold_items = getattr(ctx, "cold", []) or []

        query_terms = {"asyncio", "concurrent", "programming", "event", "loop"}
        for item in cold_items:
            text = getattr(item, "text", str(item)).lower()
            assert any(t in text for t in query_terms), (
                f"Zero-overlap decoy in cold results: {text!r}"
            )


@test_group("Cold Lexical Filter")
def test_matching_content_not_over_filtered():
    """Matching content appears in working memory (filter not overly aggressive)."""
    with TempDir() as d:
        pm = _make_pm(d)
        pm.add_turn("user", "How does asyncio handle the event loop?")
        pm.add_turn("assistant", "asyncio uses a single-threaded event loop.")

        ctx = pm.get_context(query="asyncio event loop", max_tokens=1000)
        working = getattr(ctx, "working", []) or []
        all_text = " ".join(
            getattr(item, "text", str(item)) for item in working
        ).lower()
        assert "asyncio" in all_text, (
            "Matching content over-filtered; asyncio not in working memory"
        )
