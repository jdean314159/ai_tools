"""Tests for relevance threshold filtering."""
from __future__ import annotations
import tempfile
from pathlib import Path
from engram_lite import ProjectMemory


def test_default_threshold_set():
    """Default threshold should be 0.4 (vector) and 0.0 (final)."""
    with tempfile.TemporaryDirectory() as d:
        with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as mem:
            assert mem._vector_similarity_threshold == 0.4
            assert mem._min_relevance_score == 0.0


def test_custom_thresholds_in_init():
    """Construction-time thresholds are honored."""
    with tempfile.TemporaryDirectory() as d:
        with ProjectMemory(
            base_dir=d, project_id="p", session_id="s1",
            vector_similarity_threshold=0.6,
            min_relevance_score=0.05,
        ) as mem:
            assert mem._vector_similarity_threshold == 0.6
            assert mem._min_relevance_score == 0.05


def test_threshold_disabled_with_zero():
    """Threshold of 0.0 disables filtering (returns all results)."""
    with tempfile.TemporaryDirectory() as d:
        with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as mem:
            for i in range(5):
                mem.store_episode(
                    f"Test episode {i} about topic {i}.",
                    importance=0.5, bypass_filter=True,
                )
            # No threshold = all results returned
            results = mem.search_episodes("topic", n=10, min_relevance=0.0)
            assert len(results) >= 1


def test_high_threshold_filters_results():
    """Setting a very high threshold filters out everything."""
    with tempfile.TemporaryDirectory() as d:
        with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as mem:
            for i in range(5):
                mem.store_episode(
                    f"Test episode {i} about random topic.",
                    importance=0.5, bypass_filter=True,
                )
            # Impossibly high threshold filters everything
            results = mem.search_episodes("topic", n=10, min_relevance=10.0)
            assert results == []


def test_per_call_threshold_overrides_instance():
    """Per-call min_relevance overrides instance default."""
    with tempfile.TemporaryDirectory() as d:
        with ProjectMemory(
            base_dir=d, project_id="p", session_id="s1",
            min_relevance_score=10.0,  # Filter everything by default
        ) as mem:
            mem.store_episode(
                "Test episode about a specific topic.",
                importance=0.5, bypass_filter=True,
            )
            # Default would filter all; override with 0.0
            results = mem.search_episodes("topic", n=5, min_relevance=0.0)
            assert len(results) >= 1


def test_threshold_telemetry():
    """Telemetry includes threshold filter counts."""
    events = []
    from engram_lite import Telemetry
    tel = Telemetry()
    tel.add_sink(lambda e: events.append(e))

    with tempfile.TemporaryDirectory() as d:
        with ProjectMemory(
            base_dir=d, project_id="p", session_id="s1",
            telemetry=tel,
        ) as mem:
            mem.store_episode(
                "Test episode about a topic.",
                importance=0.5, bypass_filter=True,
            )
            mem.search_episodes("topic", n=5)

    search_events = [e for e in events if e.event_type == "search_completed"]
    assert search_events
    data = search_events[-1].data
    assert "vector_similarity_threshold" in data
    assert "min_relevance" in data
    assert "vector_filtered_count" in data
    assert "relevance_filtered_count" in data
