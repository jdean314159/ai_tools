from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_harness_core import TraceEvent


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExchangeEvent:
    event_id: int
    event_type: str
    actor: str
    summary: str
    run_id: str
    thread_id: str
    body: str = ""
    target: str | None = None
    related_files: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    @property
    def preview(self) -> str:
        text = self.body.strip() or self.summary
        return text if len(text) <= 120 else text[:117] + "..."

    def to_trace_event(self) -> TraceEvent:
        return TraceEvent(
            event_type=f"agent_coordination.{self.event_type}",
            source_package="examples.agent_coordination_teaching",
            source_component="ExchangeRecorder",
            payload={
                "event_id": self.event_id,
                "run_id": self.run_id,
                "thread_id": self.thread_id,
                "actor": self.actor,
                "target": self.target,
                "summary": self.summary,
                "related_files": list(self.related_files),
                "metadata": dict(self.metadata),
            },
            severity="warning" if self.event_type.endswith("warning") else "info",
            message=self.summary,
            tags=("agent", "coordination", self.event_type),
        )


class ExchangeRecorder:
    """Append-only exchange log with full message bodies saved as artifacts."""

    def __init__(self, run_dir: Path, *, run_id: str, thread_id: str) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.thread_id = thread_id
        self.messages_dir = run_dir / "messages"
        self.messages_dir.mkdir(parents=True, exist_ok=True)
        self._events: list[ExchangeEvent] = []
        self._next_id = 1

    @property
    def events(self) -> list[ExchangeEvent]:
        return list(self._events)

    def record(
        self,
        event_type: str,
        *,
        actor: str,
        summary: str,
        body: str = "",
        target: str | None = None,
        related_files: list[str] | tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> ExchangeEvent:
        event = ExchangeEvent(
            event_id=self._next_id,
            event_type=event_type,
            actor=actor,
            target=target,
            summary=summary,
            body=body,
            run_id=self.run_id,
            thread_id=self.thread_id,
            related_files=tuple(related_files),
            metadata=dict(metadata or {}),
        )
        self._next_id += 1
        self._events.append(event)
        self._persist(event)
        return event

    def find(self, event_id: int) -> ExchangeEvent | None:
        return next((event for event in self._events if event.event_id == event_id), None)

    def _persist(self, event: ExchangeEvent) -> None:
        body_path = None
        if event.body:
            body_path = self.messages_dir / f"{event.event_id:06d}.md"
            body_path.write_text(event.body, encoding="utf-8")

        payload = asdict(event)
        payload["created_at"] = event.created_at.isoformat()
        payload["body_preview"] = event.preview
        payload["body_path"] = str(body_path.relative_to(self.run_dir)) if body_path else None
        payload.pop("body", None)

        with (self.run_dir / "exchanges.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str, sort_keys=True) + "\n")
        with (self.run_dir / "trace_events.jsonl").open("a", encoding="utf-8") as handle:
            trace = event.to_trace_event()
            handle.write(json.dumps(asdict(trace), default=str, sort_keys=True) + "\n")
