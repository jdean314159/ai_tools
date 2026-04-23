"""
Unit tests for EventBus and MemoryDaemon.

All tests are synchronous, CPU-only, no LLM calls, no ChromaDB/SQLite.
MemoryDaemon tests use a minimal mock ProjectMemory that records calls.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from engram.memory.event_bus import (
    DEFAULT_QUEUE_MAXSIZE,
    MERGE_THRESHOLD,
    EventBus,
    TurnEvent,
)


# ---------------------------------------------------------------------------
# TurnEvent tests
# ---------------------------------------------------------------------------

class TestTurnEvent:
    def test_priority_is_negated_importance(self):
        e = TurnEvent(importance=0.8, role="user", text="hi")
        assert e.priority == pytest.approx(-0.8)

    def test_ordering_higher_importance_first(self):
        lo = TurnEvent(importance=0.3, role="user", text="lo")
        hi = TurnEvent(importance=0.9, role="user", text="hi")
        assert hi < lo  # min-heap: higher importance = lower priority value

    def test_merge_concatenates_text(self):
        a = TurnEvent(importance=0.5, role="user", text="first")
        b = TurnEvent(importance=0.7, role="assistant", text="second")
        merged = a.merge(b)
        assert "first" in merged.text
        assert "second" in merged.text

    def test_merge_keeps_max_importance(self):
        a = TurnEvent(importance=0.5, role="user", text="a")
        b = TurnEvent(importance=0.9, role="user", text="b")
        merged = a.merge(b)
        assert merged.importance == pytest.approx(0.9)

    def test_merge_keeps_older_role(self):
        a = TurnEvent(importance=0.5, role="user", text="a")
        b = TurnEvent(importance=0.7, role="assistant", text="b")
        merged = a.merge(b)
        assert merged.role == "user"  # older event's role

    def test_merge_records_both_roles_in_metadata(self):
        a = TurnEvent(importance=0.5, role="user", text="a")
        b = TurnEvent(importance=0.7, role="assistant", text="b")
        merged = a.merge(b)
        assert "merged_roles" in merged.metadata
        assert set(merged.metadata["merged_roles"]) == {"user", "assistant"}

    def test_merge_sets_merged_flag(self):
        a = TurnEvent(importance=0.5, role="user", text="a")
        b = TurnEvent(importance=0.5, role="user", text="b")
        merged = a.merge(b)
        assert merged.metadata["merged"] is True

    def test_merge_increments_merged_count(self):
        a = TurnEvent(importance=0.5, role="user", text="a")
        b = TurnEvent(importance=0.5, role="user", text="b")
        m1 = a.merge(b)
        m2 = m1.merge(b)
        assert m2.metadata["merged_count"] == 3

    def test_merge_keeps_older_session_id(self):
        a = TurnEvent(importance=0.5, role="user", text="a", session_id="sess-1")
        b = TurnEvent(importance=0.7, role="user", text="b", session_id="sess-2")
        merged = a.merge(b)
        assert merged.session_id == "sess-1"

    def test_merge_keeps_max_timestamp(self):
        a = TurnEvent(importance=0.5, role="user", text="a", timestamp=1000.0)
        b = TurnEvent(importance=0.5, role="user", text="b", timestamp=2000.0)
        merged = a.merge(b)
        assert merged.timestamp == pytest.approx(2000.0)

    def test_cross_session_merge_logs_warning(self, caplog):
        import logging
        a = TurnEvent(importance=0.5, role="user", text="a", session_id="s1")
        b = TurnEvent(importance=0.5, role="user", text="b", session_id="s2")
        with caplog.at_level(logging.WARNING, logger="engram.memory.event_bus"):
            a.merge(b)
        assert any("different sessions" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# EventBus tests
# ---------------------------------------------------------------------------

class TestEventBus:
    def _event(self, importance: float = 0.5, role: str = "user", text: str = "hi") -> TurnEvent:
        return TurnEvent(importance=importance, role=role, text=text)

    def test_put_and_get_basic(self):
        bus = EventBus(maxsize=10)
        e = self._event()
        result = bus.put(e)
        assert result == "queued"
        assert bus.qsize() == 1
        got = bus.get(timeout=0.1)
        assert got is not None
        assert got.text == "hi"

    def test_stats_track_enqueued(self):
        bus = EventBus(maxsize=10)
        bus.put(self._event())
        bus.put(self._event())
        stats = bus.get_stats()
        assert stats["enqueued"] == 2
        assert stats["dropped"] == 0
        assert stats["merged"] == 0

    def test_get_returns_none_on_timeout(self):
        bus = EventBus(maxsize=10)
        result = bus.get(timeout=0.05)
        assert result is None

    def test_full_queue_drops_low_importance(self):
        bus = EventBus(maxsize=2)
        bus.put(self._event(importance=0.5))
        bus.put(self._event(importance=0.5))
        # Queue full; low importance → drop
        low = self._event(importance=MERGE_THRESHOLD - 0.1)
        result = bus.put(low)
        assert result == "dropped"
        assert bus.get_stats()["dropped"] == 1

    def test_full_queue_merges_high_importance(self):
        bus = EventBus(maxsize=2)
        bus.put(self._event(importance=0.5, text="first"))
        bus.put(self._event(importance=0.5, text="second"))
        # Queue full; high importance → merge with oldest
        high = self._event(importance=MERGE_THRESHOLD + 0.1, text="important")
        result = bus.put(high)
        assert result == "merged"
        assert bus.get_stats()["merged"] == 1
        # Queue should still have 2 items (one replaced by merged)
        assert bus.qsize() == 2

    def test_priority_queue_order(self):
        """Higher importance events should be dequeued first."""
        bus = EventBus(maxsize=10)
        bus.put(self._event(importance=0.3, text="low"))
        bus.put(self._event(importance=0.9, text="high"))
        bus.put(self._event(importance=0.6, text="mid"))

        first = bus.get(timeout=0.1)
        assert first is not None
        assert first.text == "high"

    def test_task_done_does_not_raise(self):
        bus = EventBus(maxsize=10)
        bus.put(self._event())
        bus.get(timeout=0.1)
        bus.task_done()  # should not raise

    def test_default_maxsize(self):
        bus = EventBus()
        assert bus._maxsize == DEFAULT_QUEUE_MAXSIZE

    def test_thread_safety(self):
        """Multiple producer threads should not corrupt enqueued count."""
        bus = EventBus(maxsize=500)
        errors = []

        def producer():
            try:
                for _ in range(20):
                    bus.put(self._event())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=producer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert bus.get_stats()["enqueued"] == 100


# ---------------------------------------------------------------------------
# MemoryDaemon tests
# ---------------------------------------------------------------------------

@dataclass
class _FakeIngestor:
    """Records process_turn / apply calls without doing real work."""
    calls: list = field(default_factory=list)

    def process_turn(self, role, content, metadata=None, paired_text=None):
        self.calls.append(("process_turn", role, content))
        return {"store": True, "role": role}

    def apply(self, decision):
        return {"episode_id": "fake-id", "semantic_writes": 0}


@dataclass
class _FakeWorking:
    def get_recent(self, n):
        return []


class _FakeProjectMemory:
    def __init__(self):
        self.project_id = "test-project"
        self.session_id = "test-session"
        self.ingestor = _FakeIngestor()
        self.working = _FakeWorking()
        self.semantic = None


class TestMemoryDaemon:
    def _make_daemon(self):
        from engram.memory.daemon import MemoryDaemon
        pm = _FakeProjectMemory()
        bus = EventBus(maxsize=50)

        # Patch config loading and cognitive/reflex to avoid file I/O and LLM
        with patch("engram.memory.daemon.MemoryDaemon._load_cognitive_config", return_value=None):
            daemon = MemoryDaemon(pm, bus)
        return daemon, pm, bus

    def test_start_and_stop(self):
        daemon, pm, bus = self._make_daemon()
        daemon.start()
        assert daemon._thread.is_alive()
        daemon.stop(timeout=2.0)
        assert not daemon._thread.is_alive()

    def test_processes_enqueued_event(self):
        daemon, pm, bus = self._make_daemon()
        daemon.start()

        event = TurnEvent(importance=0.7, role="user", text="hello from test")
        bus.put(event)

        # Give daemon time to process
        deadline = time.time() + 2.0
        while time.time() < deadline and daemon._processed < 1:
            time.sleep(0.05)

        daemon.stop(timeout=2.0)
        assert daemon._processed >= 1
        assert daemon._errors == 0

    def test_ingestor_called_with_correct_role(self):
        daemon, pm, bus = self._make_daemon()
        daemon.start()

        bus.put(TurnEvent(importance=0.7, role="user", text="test message"))

        deadline = time.time() + 2.0
        while time.time() < deadline and len(pm.ingestor.calls) < 1:
            time.sleep(0.05)

        daemon.stop(timeout=2.0)

        assert any(call[1] == "user" for call in pm.ingestor.calls), \
            f"Expected 'user' role in calls: {pm.ingestor.calls}"

    def test_get_stats_structure(self):
        daemon, pm, bus = self._make_daemon()
        stats = daemon.get_stats()
        assert "running" in stats
        assert "processed" in stats
        assert "errors" in stats
        assert "enqueued" in stats

    def test_errors_counted_on_ingestor_failure(self):
        daemon, pm, bus = self._make_daemon()
        pm.ingestor.apply = lambda d: (_ for _ in ()).throw(RuntimeError("boom"))

        daemon.start()
        bus.put(TurnEvent(importance=0.7, role="user", text="will fail"))

        deadline = time.time() + 2.0
        while time.time() < deadline and (daemon._processed + daemon._errors) < 1:
            time.sleep(0.05)

        daemon.stop(timeout=2.0)
        assert daemon._errors >= 1

    def test_stop_drains_remaining_events(self):
        daemon, pm, bus = self._make_daemon()
        # Don't start — stop() drain path should handle events queued before start
        for _ in range(3):
            bus.put(TurnEvent(importance=0.5, role="user", text="drain me"))

        daemon.start()
        daemon.stop(timeout=2.0)

        total = daemon._processed + daemon._errors
        assert total >= 3, f"Expected drain to process 3 events, got {total}"
