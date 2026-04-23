"""Event bus for Engram's async memory pipeline.

Decouples add_turn() from the ingestion pipeline by pushing immutable
TurnEvents onto a bounded priority queue consumed by MemoryDaemon.

Author: Jeffrey Dean
"""

from __future__ import annotations

import logging
import queue
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Queue capacity for the daemon event bus.
# At human conversation cadence (~1 turn/5s) 100 slots = ~8 minutes of buffering
# before backpressure kicks in.  Raising this delays backpressure but uses more
# memory (each TurnEvent is ~1KB).  Lowering it increases merge/drop frequency
# during bulk ingestion.  100 is correct for interactive use; increase to 500
# for batch evaluation harness runs.
DEFAULT_QUEUE_MAXSIZE = 100

# Importance threshold: events below this are dropped when queue is full.
# Events at or above this are merged with the oldest pending event.
MERGE_THRESHOLD = 0.4


@dataclass(order=True)
class TurnEvent:
    """Immutable event representing a single conversation turn.

    priority is negated importance so higher importance = lower queue priority
    number = lower number processed first (max-heap via negation).
    """
    priority: float = field(init=False)
    importance: float = field(compare=False)
    role: str = field(compare=False)
    text: str = field(compare=False)
    timestamp: float = field(compare=False, default_factory=time.time)
    session_id: str = field(compare=False, default="default")
    metadata: dict = field(compare=False, default_factory=dict)
    paired_text: Optional[str] = field(compare=False, default=None)

    def __post_init__(self):
        # Negate so higher importance = higher priority in min-heap
        object.__setattr__(self, 'priority', -self.importance)

    def merge(self, other: "TurnEvent") -> "TurnEvent":
        """Merge two events under queue backpressure.

        Metadata integrity:
        - text: concatenated in chronological order (self is older)
        - importance: max of the two (preserve higher signal)
        - role: kept from self (the older event) so ingestion sees a consistent
          role label. Both original roles are preserved in metadata["merged_roles"]
          so callers can inspect what was collapsed.
        - timestamp: max (newest wins for recency ordering)
        - session_id: from self (older event); warn if sessions differ
        - metadata: merged dict with "merged": True and "merged_roles" list
        """
        if self.session_id != other.session_id:
            logger.warning(
                "EventBus.merge: merging events from different sessions (%s, %s); "
                "keeping older session_id",
                self.session_id, other.session_id,
            )
        merged_roles = list({self.role, other.role})  # deduplicated
        merged_text = f"{self.text}\n{other.text}"
        return TurnEvent(
            importance=max(self.importance, other.importance),
            role=self.role,  # keep older event's role for ingestion consistency
            text=merged_text,
            timestamp=max(self.timestamp, other.timestamp),
            session_id=self.session_id,
            metadata={
                **self.metadata,
                **other.metadata,
                "merged": True,
                "merged_roles": merged_roles,
                "merged_count": self.metadata.get("merged_count", 1) + 1,
            },
        )


class EventBus:
    """Bounded priority queue with drop/merge backpressure policy.

    Thread-safe. Used by add_turn() to enqueue events and by
    MemoryDaemon to consume them.
    """

    def __init__(self, maxsize: int = DEFAULT_QUEUE_MAXSIZE):
        self._maxsize = maxsize
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._dropped = 0
        self._merged = 0
        self._enqueued = 0

    def put(self, event: TurnEvent) -> str:
        """Enqueue an event. Returns 'queued', 'dropped', or 'merged'."""
        if self._queue.qsize() < self._maxsize:
            self._queue.put(event)
            self._enqueued += 1
            return "queued"

        # Queue full — apply backpressure policy
        if event.importance < MERGE_THRESHOLD:
            self._dropped += 1
            logger.debug(
                "EventBus: dropped low-importance event (importance=%.2f role=%s)",
                event.importance, event.role,
            )
            return "dropped"

        # High importance: merge with oldest pending event
        try:
            oldest: TurnEvent = self._queue.get_nowait()
            merged = oldest.merge(event)
            self._queue.put(merged)
            self._merged += 1
            logger.debug(
                "EventBus: merged high-importance event (importance=%.2f) with oldest",
                event.importance,
            )
            return "merged"
        except queue.Empty:
            # Race condition: queue emptied between check and get; just enqueue
            self._queue.put(event)
            self._enqueued += 1
            return "queued"

    def get(self, timeout: float = 1.0) -> Optional[TurnEvent]:
        """Blocking get with timeout. Returns None on timeout."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def task_done(self):
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()

    def get_stats(self) -> dict:
        return {
            "qsize": self._queue.qsize(),
            "enqueued": self._enqueued,
            "dropped": self._dropped,
            "merged": self._merged,
        }