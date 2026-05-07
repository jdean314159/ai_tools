"""Lightweight telemetry for Engram.

API matches engram_lite.Telemetry so engram_lite can re-export these
classes directly.  Call sites use:

    telemetry.emit(event_type, data_dict)

where event_type is a short string label and data_dict carries any
structured payload.  If you need to attach a message, put it under the
``"message"`` key in data_dict.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TelemetryEvent:
    """A single telemetry observation."""

    def __init__(
        self,
        event_type: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> None:
        self.event_type = event_type
        self.data = data
        self.timestamp = timestamp if timestamp is not None else time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class Telemetry:
    """Pluggable telemetry emitter.

    Add sinks with :meth:`add_sink`.  Emit events with
    :meth:`emit`.  No-ops when no sinks are registered or when
    disabled.
    """

    def __init__(self) -> None:
        self._sinks: List[Callable[[TelemetryEvent], None]] = []
        self._enabled: bool = True

    @property
    def enabled(self) -> bool:
        """Whether telemetry emission is enabled."""
        return self._enabled

    @property
    def sinks(self) -> List[Callable[[TelemetryEvent], None]]:
        """Registered telemetry sinks as a defensive copy."""
        return list(self._sinks)

    @property
    def sink(self) -> Optional[Callable[[TelemetryEvent], None]]:
        """Compatibility accessor for the first registered sink."""
        return self._sinks[0] if self._sinks else None

    def add_sink(self, sink: Callable[[TelemetryEvent], None]) -> None:
        self._sinks.append(sink)

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if not self._enabled or not self._sinks:
            return
        event = TelemetryEvent(event_type, data)
        for sink in self._sinks:
            try:
                sink(event)
            except Exception as exc:
                logger.debug("Telemetry sink error: %s", exc)

    def disable(self) -> None:
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True


def log_sink(event: TelemetryEvent) -> None:
    """Built-in sink: log to Python logging at INFO level."""
    logger.info("Telemetry: %s - %s", event.event_type, event.data)


def json_file_sink(path: str) -> Callable[[TelemetryEvent], None]:
    """Built-in sink: append JSON lines to *path*."""
    from pathlib import Path as _Path

    def sink(event: TelemetryEvent) -> None:
        p = _Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")

    return sink
