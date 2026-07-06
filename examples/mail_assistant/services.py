"""Snapshot, classification, and view assembly for the mail assistant."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import threading
from typing import Callable, Iterable

from mail_lib.personal_rules import ClassifiedMessage, PersonalRule, classify_message
from mail_lib.thunderbird import Identity, MailMessage, MessageMetadata, iter_messages
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
        self.store.put_mail_snapshot(str(self.profile.resolve()), _encode_snapshot(loaded))
        with self._lock:
            self._state = SnapshotState(loaded, self._state.revision + 1)
            return self._state

    def load_cached(self) -> SnapshotState:
        payload = self.store.get_mail_snapshot(str(self.profile.resolve()))
        if payload is None:
            return self.state
        loaded = _decode_snapshot(payload)
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

    def remove_message(self, header_message_id: str) -> None:
        self.remove_messages((header_message_id,))

    def remove_messages(self, header_message_ids: Iterable[str]) -> None:
        selected = set(header_message_ids)
        with self._lock:
            remaining = tuple(
                item for item in self._state.messages if item.header_message_id not in selected
            )
            if len(remaining) == len(self._state.messages):
                raise KeyError(next(iter(selected), ""))
            self._state = SnapshotState(remaining, self._state.revision + 1)
        self.store.put_mail_snapshot(str(self.profile.resolve()), _encode_snapshot(remaining))


def _encode_snapshot(messages: tuple[MailMessage, ...]) -> str:
    encoded = []
    for message in messages:
        metadata = message.metadata
        encoded.append(
            {
                "header_message_id": message.header_message_id,
                "subject": message.subject,
                "body": message.body,
                "sender": message.sender,
                "recipients": message.recipients,
                "date": message.date,
                "source_folder": message.source_folder,
                "signal_folders": message.signal_folders,
                "mbox_path": str(message.mbox_path) if message.mbox_path else None,
                "metadata": None if metadata is None else {
                    "header_message_id": metadata.header_message_id,
                    "message_key": metadata.message_key,
                    "folder_id": metadata.folder_id,
                    "conversation_id": metadata.conversation_id,
                    "date": metadata.date,
                    "sender_id": metadata.sender_id,
                    "recipient_ids": metadata.recipient_ids,
                    "sender": None if metadata.sender is None else {
                        "contact_id": metadata.sender.contact_id,
                        "name": metadata.sender.name,
                        "address": metadata.sender.address,
                    },
                    "recipients": [
                        {"contact_id": item.contact_id, "name": item.name, "address": item.address}
                        for item in metadata.recipients
                    ],
                    "flags": metadata.flags,
                    "folder_uri": metadata.folder_uri,
                    "folder_name": metadata.folder_name,
                },
            }
        )
    return json.dumps(encoded, ensure_ascii=False, separators=(",", ":"))


def _decode_snapshot(payload: str) -> tuple[MailMessage, ...]:
    messages = []
    for raw in json.loads(payload):
        raw_metadata = raw["metadata"]
        metadata = None
        if raw_metadata is not None:
            sender = raw_metadata["sender"]
            metadata = MessageMetadata(
                header_message_id=raw_metadata["header_message_id"],
                message_key=raw_metadata["message_key"],
                folder_id=raw_metadata["folder_id"],
                conversation_id=raw_metadata["conversation_id"],
                date=raw_metadata["date"],
                sender_id=raw_metadata["sender_id"],
                recipient_ids=tuple(raw_metadata["recipient_ids"]),
                sender=Identity(**sender) if sender else None,
                recipients=tuple(Identity(**item) for item in raw_metadata["recipients"]),
                flags=dict(raw_metadata["flags"]),
                folder_uri=raw_metadata["folder_uri"],
                folder_name=raw_metadata["folder_name"],
            )
        messages.append(MailMessage(
            header_message_id=raw["header_message_id"],
            subject=raw["subject"],
            body=raw["body"],
            sender=raw["sender"],
            recipients=tuple(raw["recipients"]),
            date=raw["date"],
            source_folder=raw["source_folder"],
            signal_folders=tuple(raw["signal_folders"]),
            metadata=metadata,
            mbox_path=Path(raw["mbox_path"]) if raw["mbox_path"] else None,
        ))
    return tuple(messages)
