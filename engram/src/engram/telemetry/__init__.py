"""Lightweight telemetry/event sink.

Provides structured events emitted during runtime
(failover decisions, prompt compression, retrieval choices, etc.).

Design goals:
  - Dependency-light (stdlib only)
  - Opt-in (no overhead unless a sink is registered)
  - Supports console/logging and JSONL file sinks

engram_lite re-exports Telemetry, TelemetryEvent, log_sink, and
json_file_sink directly from this package.
"""

from .core import Telemetry, TelemetryEvent, log_sink, json_file_sink
from .sinks import LoggingSink, JsonlFileSink

__all__ = [
    "Telemetry", "TelemetryEvent",
    "log_sink", "json_file_sink",
    "LoggingSink", "JsonlFileSink",
]
