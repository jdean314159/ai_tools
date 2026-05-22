"""Tests for hybrid retrieval (RRF) module."""
from __future__ import annotations
import pytest
from engram.retrieval.hybrid import reciprocal_rank_fusion, hybrid_episode_search
import time


# ---------------------------------------------------------------------------
# reciprocal_rank_fusion
# ---------------------------------------------------------------------------

def test_rrf_single_list():
    """Single list: RRF score = 1/(k+rank). Order preserved."""
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    result = reciprocal_rank_fusion([items])
    ids = [r["id"] for r in result]
    assert ids == ["a", "b", "c"]
    # Scores decrease with rank
    assert result[0]["rrf_score"] > result[1]["rrf_score"] > result[2]["rrf_score"]


def test_rrf_two_lists_agreement():
    """When both lists agree on top item, it scores highest."""
    list1 = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    list2 = [{"id": "a"}, {"id": "c"}, {"id": "b"}]
    result = reciprocal_rank_fusion([list1, list2])
    assert result[0]["id"] == "a"


def test_rrf_two_lists_disagreement():
    """Item ranked first in both lists beats items ranked first in one."""
    list1 = [{"id": "a"}, {"id": "b"}]
    list2 = [{"id": "b"}, {"id": "a"}]
    result = reciprocal_rank_fusion([list1, list2])
    # Both appear in both lists, but relative scores should be close
    ids = {r["id"] for r in result}
    assert ids == {"a", "b"}
    # Combined scores should be equal (both ranked 1st and 2nd)
    assert abs(result[0]["rrf_score"] - result[1]["rrf_score"]) < 0.001


def test_rrf_disjoint_lists():
    """Items in one list only still get scored."""
    list1 = [{"id": "a"}]
    list2 = [{"id": "b"}]
    result = reciprocal_rank_fusion([list1, list2])
    assert len(result) == 2
    # Both ranked 1st in their respective list, equal scores
    assert abs(result[0]["rrf_score"] - result[1]["rrf_score"]) < 0.001


def test_rrf_empty_lists():
    """Empty inputs return empty output."""
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[]]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_missing_id():
    """Items without id key are skipped."""
    items = [{"id": "a"}, {"no_id": "x"}, {"id": "b"}]
    result = reciprocal_rank_fusion([items])
    ids = [r["id"] for r in result]
    assert "a" in ids and "b" in ids
    assert len(result) == 2


def test_rrf_custom_k():
    """Custom k changes score magnitude but not relative order."""
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    result_k60 = reciprocal_rank_fusion([items], k=60)
    result_k1 = reciprocal_rank_fusion([items], k=1)
    # Order same
    assert [r["id"] for r in result_k60] == [r["id"] for r in result_k1]
    # Low k means higher scores and more spread
    assert result_k1[0]["rrf_score"] > result_k60[0]["rrf_score"]


def test_rrf_preserves_item_data():
    """Original item data is preserved in fused results."""
    items = [{"id": "a", "text": "hello", "importance": 0.9}]
    result = reciprocal_rank_fusion([items])
    assert result[0]["text"] == "hello"
    assert result[0]["importance"] == 0.9
    assert "rrf_score" in result[0]


# ---------------------------------------------------------------------------
# hybrid_episode_search
# ---------------------------------------------------------------------------

def make_episode(id_, text, importance=0.5, age_days=0):
    return {
        "id": id_,
        "text": text,
        "importance": importance,
        "created_at": time.time() - (age_days * 86400),
    }


def test_hybrid_no_results():
    result = hybrid_episode_search(
        query="test", query_embedding=None,
        vector_results=None, text_results=None,
    )
    assert result == []


def test_hybrid_text_only():
    """With only text results, returns them with final_score set."""
    text_results = [
        make_episode("a", "python programming", importance=0.8),
        make_episode("b", "java programming", importance=0.5),
    ]
    result = hybrid_episode_search(
        query="python", query_embedding=None,
        vector_results=None, text_results=text_results,
    )
    assert len(result) == 2
    assert all("final_score" in r for r in result)


def test_hybrid_vector_only():
    """With only vector results, returns them with final_score."""
    vector_results = [
        make_episode("a", "semantic match", importance=0.9),
        make_episode("b", "another match", importance=0.6),
    ]
    result = hybrid_episode_search(
        query="test", query_embedding=[0.1] * 8,
        vector_results=vector_results, text_results=None,
    )
    assert len(result) == 2
    assert all("final_score" in r for r in result)


def test_hybrid_combined():
    """Combined vector+text produces merged results."""
    vector_results = [make_episode("a", "vector match"), make_episode("b", "both match")]
    text_results = [make_episode("b", "both match"), make_episode("c", "text match")]
    result = hybrid_episode_search(
        query="match", query_embedding=[0.1] * 8,
        vector_results=vector_results, text_results=text_results,
    )
    ids = {r["id"] for r in result}
    assert ids == {"a", "b", "c"}
    # "b" appears in both lists, should have highest score
    assert result[0]["id"] == "b"


def test_recency_boost_applied():
    """Recent episodes score higher than old ones with same base score."""
    recent = make_episode("recent", "test text query", importance=0.5, age_days=0)
    old = make_episode("old", "test text query", importance=0.5, age_days=60)
    result = hybrid_episode_search(
        query="test", query_embedding=None,
        text_results=[recent, old], recency_boost=True,
    )
    recent_score = next(r["final_score"] for r in result if r["id"] == "recent")
    old_score = next(r["final_score"] for r in result if r["id"] == "old")
    assert recent_score > old_score


def test_recency_boost_disabled():
    """Disabling recency boost should equalize scores for same-importance items."""
    recent = make_episode("recent", "test", importance=0.5, age_days=0)
    old = make_episode("old", "test", importance=0.5, age_days=60)
    result = hybrid_episode_search(
        query="test", query_embedding=None,
        text_results=[recent, old], recency_boost=False, importance_boost=False,
    )
    recent_score = next(r["final_score"] for r in result if r["id"] == "recent")
    old_score = next(r["final_score"] for r in result if r["id"] == "old")
    assert abs(recent_score - old_score) < 0.001


def test_importance_boost_applied():
    """High importance episodes score higher."""
    high = make_episode("high", "test content", importance=1.0)
    low = make_episode("low", "test content", importance=0.0)
    result = hybrid_episode_search(
        query="test", query_embedding=None,
        text_results=[high, low],
        recency_boost=False, importance_boost=True,
    )
    high_score = next(r["final_score"] for r in result if r["id"] == "high")
    low_score = next(r["final_score"] for r in result if r["id"] == "low")
    assert high_score > low_score


def test_importance_boost_range():
    """Importance multiplier should be in [0.8, 1.2] range."""
    items = [
        make_episode("zero", "test", importance=0.0),
        make_episode("half", "test", importance=0.5),
        make_episode("full", "test", importance=1.0),
    ]
    result = hybrid_episode_search(
        query="test", query_embedding=None,
        text_results=items,
        recency_boost=False, importance_boost=True,
    )
    scores = {r["id"]: r["final_score"] for r in result}
    # At importance=0: multiplier = 0.8 + 0*0.4 = 0.8
    # At importance=1: multiplier = 0.8 + 1*0.4 = 1.2
    # Ratio should be 1.2/0.8 = 1.5
    ratio = scores["full"] / scores["zero"]
    assert 1.4 < ratio < 1.6
