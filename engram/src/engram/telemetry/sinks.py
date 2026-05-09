"""Concrete sinks for engram telemetry.

LoggingSink and JsonlFileSink are kept for backward compatibility with
code that constructed them explicitly.  New code should prefer the
module-level ``log_sink`` and ``json_file_sink`` functions from
``engram.telemetry``.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .core import TelemetryEvent


class LoggingSink:
    """Emit telemetry events via Python logging."""

    def __init__(
        self,
        logger_name: str = "engram.telemetry",
        level: int = logging.INFO,
    ) -> None:
        self.logger = logging.getLogger(logger_name)
        self.level = level

    def __call__(self, event: TelemetryEvent) -> None:
        self.logger.log(
            self.level,
            "telemetry %s %s",
            event.event_type,
            event.data,
        )


class JsonlFileSink:
    """Append telemetry events to a JSONL file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, event: TelemetryEvent) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")
