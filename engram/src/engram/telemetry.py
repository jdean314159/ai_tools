from __future__ import annotations
import time
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TelemetryEvent:
    def __init__(self, event_type: str, data: Dict[str, Any], timestamp: Optional[float] = None):
        self.event_type = event_type
        self.data = data
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict:
        return {"event_type": self.event_type, "data": self.data, "timestamp": self.timestamp}


class Telemetry:
    """Pluggable telemetry system. Add sinks to receive events."""

    def __init__(self):
        self._sinks: List[Callable[[TelemetryEvent], None]] = []
        self._enabled = True

    def add_sink(self, sink: Callable[[TelemetryEvent], None]):
        self._sinks.append(sink)

    def emit(self, event_type: str, data: Dict[str, Any]):
        if not self._enabled or not self._sinks:
            return
        event = TelemetryEvent(event_type, data)
        for sink in self._sinks:
            try:
                sink(event)
            except Exception as e:
                logger.debug(f"Telemetry sink error: {e}")

    def disable(self):
        self._enabled = False

    def enable(self):
        self._enabled = True


def log_sink(event: TelemetryEvent):
    logger.info(f"Telemetry: {event.event_type} - {event.data}")


def json_file_sink(path: str) -> Callable[[TelemetryEvent], None]:
    import json
    from pathlib import Path

    def sink(event: TelemetryEvent):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    return sink
