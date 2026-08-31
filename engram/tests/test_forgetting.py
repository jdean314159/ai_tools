"""Tests for forgetting policy: decay, pruning, superseded cleanup."""

from __future__ import annotations
import time
import pytest
from pathlib import Path
from engram.semantic.graph import SemanticGraph
from engram.semantic.forgetting import ForgettingConfig, ForgettingPolicy


def make_graph(tmp_path=None):
    path = Path(tmp_path) / "graph.json" if tmp_path else None
    return SemanticGraph(persist_path=path)


def add_fact(
    graph, fact_id, subject="subject", value="value", confidence=0.5, age_days=0, access_count=0
):
    """Helper to add a fact with backdated timestamps."""
    graph.add_fact(fact_id, "preference", subject, value, confidence=confidence)
    now = time.time()
    past = now - (age_days * 86400)
    graph.graph.nodes[fact_id]["created_at"] = past
    graph.graph.nodes[fact_id]["accessed_at"] = past
    graph.graph.nodes[fact_id]["access_count"] = access_count


# ---------------------------------------------------------------------------
# ForgettingConfig validation
# ---------------------------------------------------------------------------


def test_config_valid():
    config = ForgettingConfig(decay_rate=0.9, min_confidence=0.1)
    assert config.decay_rate == 0.9


def test_config_invalid_decay_rate():
    with pytest.raises(ValueError):
        ForgettingConfig(decay_rate=1.5)


def test_config_invalid_min_confidence():
    with pytest.raises(ValueError):
        ForgettingConfig(min_confidence=-0.1)


def test_config_defaults():
    config = ForgettingConfig()
    assert config.enable_decay is True
    assert config.enable_pruning is True
    assert config.enable_superseded_cleanup is True
    assert config.decay_rate == 0.95
    assert config.min_confidence == 0.1
    assert config.min_age_days == 30
    assert config.superseded_age_days == 90


# ---------------------------------------------------------------------------
# Importance decay
# ---------------------------------------------------------------------------


def test_decay_reduces_confidence():
    graph = make_graph()
    add_fact(graph, "fact:001", confidence=1.0, age_days=14)  # 2 weeks unaccessed

    graph.decay_importance(decay_rate=0.5, period_days=7)

    new_conf = graph.graph.nodes["fact:001"]["confidence"]
    # 2 periods elapsed: 1.0 * 0.5^2 = 0.25
    assert abs(new_conf - 0.25) < 0.01


def test_decay_recent_fact_unchanged():
    graph = make_graph()
    add_fact(graph, "fact:001", confidence=0.8, age_days=0)

    graph.decay_importance(decay_rate=0.5, period_days=7)

    new_conf = graph.graph.nodes["fact:001"]["confidence"]
    assert new_conf == 0.8  # Not decayed (0 periods elapsed)


def test_decay_floors_at_zero():
    graph = make_graph()
    add_fact(graph, "fact:001", confidence=0.001, age_days=365)

    graph.decay_importance(decay_rate=0.5, period_days=7)

    new_conf = graph.graph.nodes["fact:001"]["confidence"]
    assert new_conf >= 0.0


def test_decay_only_affects_facts():
    """Entity nodes should not be decayed."""
    graph = make_graph()
    add_fact(graph, "fact:001", subject="entity_subject", confidence=0.8, age_days=14)

    # Entity node created automatically
    entity_node = "entity:entity_subject"
    assert graph.graph.has_node(entity_node)
    assert "confidence" not in graph.graph.nodes[entity_node]

    graph.decay_importance(decay_rate=0.5, period_days=7)

    # Entity still has no confidence
    assert "confidence" not in graph.graph.nodes[entity_node]


# ---------------------------------------------------------------------------
# Low-importance pruning
# ---------------------------------------------------------------------------


def test_prune_removes_low_confidence_old_facts():
    graph = make_graph()
    add_fact(graph, "fact:old_low", confidence=0.05, age_days=40, access_count=0)
    add_fact(graph, "fact:new_high", confidence=0.9, age_days=0)

    removed = graph.forget_low_importance_facts(
        min_confidence=0.1,
        min_age_days=30,
        max_to_prune=100,
    )

    assert removed == 1
    assert not graph.graph.has_node("fact:old_low")
    assert graph.graph.has_node("fact:new_high")


def test_prune_preserves_recently_accessed():
    """Fact with low confidence but recent access is kept."""
    graph = make_graph()
    add_fact(graph, "fact:low_accessed", confidence=0.05, age_days=40)
    # Override accessed_at to be recent
    graph.graph.nodes["fact:low_accessed"]["accessed_at"] = time.time()
    graph.graph.nodes["fact:low_accessed"]["access_count"] = 5

    removed = graph.forget_low_importance_facts(min_confidence=0.1, min_age_days=30)
    assert removed == 0
    assert graph.graph.has_node("fact:low_accessed")


def test_prune_preserves_high_confidence():
    """High confidence facts are not pruned even if old."""
    graph = make_graph()
    add_fact(graph, "fact:high_old", confidence=0.9, age_days=100, access_count=0)

    removed = graph.forget_low_importance_facts(min_confidence=0.1, min_age_days=30)
    assert removed == 0


def test_prune_respects_max_limit():
    """max_to_prune limits how many facts are removed per run."""
    graph = make_graph()
    for i in range(10):
        add_fact(graph, f"fact:{i:03d}", confidence=0.01, age_days=60, access_count=0)

    removed = graph.forget_low_importance_facts(
        min_confidence=0.1,
        min_age_days=30,
        max_to_prune=3,
    )
    assert removed == 3
    assert graph.graph.number_of_nodes() > 0  # Some remain


def test_prune_empty_graph():
    """Pruning empty graph returns 0."""
    graph = make_graph()
    removed = graph.forget_low_importance_facts()
    assert removed == 0


# ---------------------------------------------------------------------------
# Superseded fact cleanup
# ---------------------------------------------------------------------------


def test_superseded_cleanup_removes_old():
    """Old superseded facts are removed after age threshold."""
    graph = make_graph()
    add_fact(graph, "fact:old", confidence=0.7, age_days=0)
    add_fact(graph, "fact:new", confidence=0.9, age_days=0)
    graph.supersede_fact("fact:old", "fact:new")

    # Backdate superseded_at to 91 days ago
    graph.graph.nodes["fact:old"]["superseded_at"] = time.time() - (91 * 86400)

    removed = graph.forget_superseded_facts(min_age_days=90)
    assert removed == 1
    assert not graph.graph.has_node("fact:old")
    assert graph.graph.has_node("fact:new")


def test_superseded_cleanup_keeps_recent():
    """Recently superseded facts are kept."""
    graph = make_graph()
    add_fact(graph, "fact:old", confidence=0.7)
    add_fact(graph, "fact:new", confidence=0.9)
    graph.supersede_fact("fact:old", "fact:new")

    removed = graph.forget_superseded_facts(min_age_days=90)
    assert removed == 0
    assert graph.graph.has_node("fact:old")


def test_superseded_cleanup_only_removes_superseded():
    """Non-superseded facts are not removed by superseded cleanup."""
    graph = make_graph()
    add_fact(graph, "fact:active", confidence=0.5, age_days=200)
    add_fact(graph, "fact:superseded_old", confidence=0.5, age_days=200)
    add_fact(graph, "fact:replacement", confidence=0.9, age_days=200)

    graph.supersede_fact("fact:superseded_old", "fact:replacement")
    graph.graph.nodes["fact:superseded_old"]["superseded_at"] = time.time() - (200 * 86400)

    removed = graph.forget_superseded_facts(min_age_days=90)
    assert removed == 1
    assert graph.graph.has_node("fact:active")


# ---------------------------------------------------------------------------
# ForgettingPolicy integration
# ---------------------------------------------------------------------------


def test_policy_runs_all_enabled():
    """Policy with all features enabled runs decay, pruning, and cleanup."""
    graph = make_graph()
    add_fact(graph, "fact:prune", confidence=0.01, age_days=60, access_count=0)
    add_fact(graph, "fact:active", confidence=0.9, age_days=0)

    config = ForgettingConfig(
        enable_decay=True,
        decay_rate=0.5,
        decay_period_days=7,
        enable_pruning=True,
        min_confidence=0.1,
        min_age_days=30,
        enable_superseded_cleanup=True,
        superseded_age_days=90,
    )
    policy = ForgettingPolicy(config)
    stats = policy.run_maintenance(graph)

    assert stats["decayed"] == 1
    assert stats["pruned"] >= 1
    assert stats["superseded_removed"] == 0


def test_policy_respects_disabled_flags():
    """Disabled features do not run."""
    graph = make_graph()
    add_fact(graph, "fact:low", confidence=0.01, age_days=60, access_count=0)

    config = ForgettingConfig(
        enable_decay=False,
        enable_pruning=False,
        enable_superseded_cleanup=False,
    )
    policy = ForgettingPolicy(config)
    stats = policy.run_maintenance(graph)

    assert stats["decayed"] == 0
    assert stats["pruned"] == 0
    assert graph.graph.has_node("fact:low")  # Not pruned


def test_policy_saves_graph(tmp_path):
    """Policy run saves the graph to disk."""
    graph = make_graph(tmp_path)
    add_fact(graph, "fact:001", confidence=0.9)

    config = ForgettingConfig()
    policy = ForgettingPolicy(config)
    policy.run_maintenance(graph)

    graph_file = tmp_path / "graph.json"
    assert graph_file.exists()
