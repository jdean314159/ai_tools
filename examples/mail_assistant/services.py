"""Snapshot, classification, and view assembly for the mail assistant."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from typing import Callable, Iterable

from mail_lib.personal_rules import ClassifiedMessage, PersonalRule, classify_message
from mail_lib.thunderbird import MailMessage, iter_messages
from mail_lib.triage import Priority

from .store import AssistantStore


PRIORITY_ORDER = (Priority.URGENT, Priority.NORMAL, Priority.LOW, Priority.IGNORE)


def thunderbird_read(message: MailMessage) -> bool:
    return bool(message.metadata and message.metadata.flags.get("read", False))


def message_datetime(message: MailMessage) -> datetime | None:
    if not message.date:
        return None
    try:
        parsed = datetime.fromisoformat(message.date)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class SnapshotState:
    messages: tuple[MailMessage, ...]
    revision: int


class MailAssistantService:
    """Own an atomically replaceable in-memory mail snapshot."""

    def __init__(
        self,
        profile: str | Path,
        store: AssistantStore,
        *,
        reader: Callable[[str | Path], Iterable[MailMessage]] = iter_messages,
    ) -> None:
        self.profile = Path(profile)
        self.store = store
        self._reader = reader
        self._lock = threading.RLock()
        self._state = SnapshotState((), 0)

    @property
    def state(self) -> SnapshotState:
        with self._lock:
            return self._state

    def refresh(self) -> SnapshotState:
        loaded = tuple(self._reader(self.profile))
        with self._lock:
            self._state = SnapshotState(loaded, self._state.revision + 1)
            return self._state

    def classify(self, rules: tuple[PersonalRule, ...]) -> tuple[ClassifiedMessage, ...]:
        return tuple(classify_message(message, rules) for message in self.state.messages)

    def visible(
        self,
        rules: tuple[PersonalRule, ...],
        *,
        view: str = "unread",
        max_age_days: int | None = None,
        now: datetime | None = None,
    ) -> dict[Priority, tuple[ClassifiedMessage, ...]]:
        if view not in {"unread", "all"}:
            raise ValueError("view must be 'unread' or 'all'")
        app_read = self.store.read_ids()
        cutoff = None
        if max_age_days is not None:
            current = now or datetime.now(timezone.utc)
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            cutoff = current.astimezone(timezone.utc) - timedelta(days=max_age_days)
        grouped: dict[Priority, list[ClassifiedMessage]] = {item: [] for item in PRIORITY_ORDER}
        for classified in self.classify(rules):
            message = classified.message
            message_date = message_datetime(message)
            if cutoff is not None and (message_date is None or message_date < cutoff):
                continue
            is_read = thunderbird_read(message) or message.header_message_id in app_read
            if view == "unread" and is_read:
                continue
            grouped[classified.triage.priority].append(classified)
        for messages in grouped.values():
            messages.sort(
                key=lambda item: message_datetime(item.message) or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
        return {priority: tuple(grouped[priority]) for priority in PRIORITY_ORDER}

    def mark_read(self, header_message_id: str) -> None:
        if header_message_id not in {item.header_message_id for item in self.state.messages}:
            raise KeyError(header_message_id)
        self.store.mark_read(header_message_id)
