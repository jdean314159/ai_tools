from __future__ import annotations

from textwrap import indent

from agent_lib import CoordinationMessage, ExternalSessionCoordinator

from .exchange import ExchangeEvent, ExchangeRecorder


class LiveConsoleMonitor:
    def __init__(
        self,
        recorder: ExchangeRecorder,
        *,
        coordinator: ExternalSessionCoordinator | None = None,
        recipients: list[str] | None = None,
    ) -> None:
        self.recorder = recorder
        self.coordinator = coordinator
        self.recipients = list(recipients or [])

    def print_event(self, event: ExchangeEvent) -> None:
        target = f" -> {event.target}" if event.target else ""
        print(f"[{event.event_id:03d}] {event.created_at:%H:%M:%S} {event.actor}{target} {event.event_type}: {event.summary}")

    def print_recent(self, *, limit: int = 10) -> None:
        print("\nRecent exchanges")
        for event in self.recorder.events[-limit:]:
            self.print_event(event)

    def open_event(self, event_id: int) -> None:
        event = self.recorder.find(event_id)
        if event is None:
            print(f"No exchange with id {event_id}.")
            return
        target = event.target or "(none)"
        print(
            f"\nMessage {event.event_id}\n"
            f"Type: {event.event_type}\n"
            f"From: {event.actor}\n"
            f"To: {target}\n"
            f"Thread: {event.thread_id}\n"
            f"Time: {event.created_at.isoformat()}\n"
            f"Files: {', '.join(event.related_files) or '(none)'}\n"
        )
        body = event.body or event.summary
        print(indent(body, "  "))

    def command_loop(self, *, phase: str = "monitor") -> None:
        print(f"\n{phase} monitor commands: help, status, open <id>, guidance <agent> <message>, broadcast <message>, continue")
        while True:
            try:
                raw = input("monitor> ").strip()
            except EOFError:
                return
            if raw in {"", "status", "messages"}:
                self.print_recent()
                continue
            if raw == "help":
                print("Commands: status/messages, open <id>, guidance <agent> <message>, broadcast <message>, continue")
                continue
            if raw in {"continue", "quit"}:
                return
            if raw.startswith("open "):
                try:
                    self.open_event(int(raw.split(maxsplit=1)[1]))
                except ValueError:
                    print("Usage: open <id>")
                continue
            if raw.startswith("guidance "):
                self._send_guidance(raw)
                continue
            if raw.startswith("broadcast "):
                self._broadcast(raw.removeprefix("broadcast ").strip())
                continue
            print("Unknown command. Type help.")

    def _send_guidance(self, raw: str) -> None:
        if self.coordinator is None:
            print("This monitor has no mailbox coordinator attached.")
            return
        parts = raw.split(maxsplit=2)
        if len(parts) < 3:
            print("Usage: guidance <agent> <message>")
            return
        recipient = parts[1]
        body = parts[2]
        message = self.coordinator.send(
            "human",
            recipient,
            kind="decision",
            subject="Human guidance",
            body=body,
            thread_id=self.recorder.thread_id,
            metadata={"source": "live_monitor"},
        )
        self._record_message(message, event_type="human_guidance_sent")
        print(f"Sent guidance to {recipient}.")

    def _broadcast(self, body: str) -> None:
        if not body:
            print("Usage: broadcast <message>")
            return
        if self.coordinator is None:
            print("This monitor has no mailbox coordinator attached.")
            return
        for recipient in self.recipients:
            message = self.coordinator.send(
                "human",
                recipient,
                kind="decision",
                subject="Human broadcast",
                body=body,
                thread_id=self.recorder.thread_id,
                metadata={"source": "live_monitor"},
            )
            self._record_message(message, event_type="human_broadcast_sent")
        print(f"Broadcast guidance to {len(self.recipients)} workers.")

    def _record_message(self, message: CoordinationMessage, *, event_type: str) -> None:
        self.recorder.record(
            event_type,
            actor=message.sender,
            target=message.recipient,
            summary=message.subject,
            body=message.body,
            metadata={
                "message_id": message.message_id,
                "kind": message.kind,
                "created_at": message.created_at.isoformat(),
            },
        )
