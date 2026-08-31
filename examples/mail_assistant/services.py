"""Snapshot, classification, and view assembly for the mail assistant."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import threading
from typing import Any, Callable, Iterable

from mail_lib.personal_rules import ClassifiedMessage, PersonalRule, classify_message
from mail_lib.thunderbird import (
    Identity,
    MailMessage,
    MessageMetadata,
    iter_messages,
    load_message_bodies,
    load_message_body,
)
from mail_lib.triage import Priority, is_bare_link_body

from .store import AssistantStore


PRIORITY_ORDER = (Priority.URGENT, Priority.NORMAL, Priority.LOW, Priority.IGNORE)
SNAPSHOT_BODY_PREVIEW_CHARS = 1_000


def thunderbird_read(message: MailMessage) -> bool:
    if message.read_state_source == "msf":
        return message.local_read
    if message.metadata and "read" in message.metadata.flags:
        return bool(message.metadata.flags["read"])
    return message.local_read


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


def _preview_message(message: MailMessage) -> MailMessage:
    if len(message.body) <= SNAPSHOT_BODY_PREVIEW_CHARS:
        return message
    return replace(
        message,
        body=message.body[:SNAPSHOT_BODY_PREVIEW_CHARS],
        body_complete=False,
        body_is_bare_link=(
            message.body_is_bare_link
            if message.body_is_bare_link is not None
            else is_bare_link_body(message.body)
        ),
    )


@dataclass(frozen=True)
class SnapshotState:
    messages: tuple[MailMessage, ...]
    revision: int
    # None means the snapshot is unbounded. 0 means legacy/unknown coverage.
    max_age_days: int | None = None
    refreshed_at: datetime | None = None
    latest_message_at: datetime | None = None

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass(frozen=True)
class VolumeStat:
    value: str
    count: int
    unread_count: int
    share: float
    most_recent: datetime | None


class MailAssistantService:
    """Own an atomically replaceable in-memory mail snapshot."""

    def __init__(
        self,
        profile: str | Path,
        store: AssistantStore,
        *,
        reader: Callable[..., Iterable[MailMessage]] = iter_messages,
        include_message: Callable[[MailMessage], bool] | None = None,
    ) -> None:
        self.profile = Path(profile)
        self.store = store
        self._reader = reader
        self._include_message = include_message or (lambda _message: True)
        self._lock = threading.RLock()
        self._state = SnapshotState((), 0, None)

    @property
    def state(self) -> SnapshotState:
        with self._lock:
            return self._state

    def refresh(
        self,
        *,
        max_age_days: int | None = None,
        now: datetime | None = None,
    ) -> SnapshotState:
        newer_than = None
        if max_age_days is not None:
            current = now or datetime.now(timezone.utc)
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            newer_than = current.astimezone(timezone.utc) - timedelta(days=max_age_days)
        reader_kwargs: dict[str, Any] = {}
        if newer_than is not None:
            reader_kwargs["newer_than"] = newer_than
        loaded = tuple(
            _preview_message(message)
            for message in self._reader(self.profile, **reader_kwargs)
            if self._include_message(message)
        )
        refreshed_at = datetime.now(timezone.utc)
        latest_message_at = _latest_message_datetime(loaded)
        self.store.put_mail_snapshot(
            str(self.profile.resolve()),
            _encode_snapshot(
                loaded,
                max_age_days=max_age_days,
                refreshed_at=refreshed_at,
                latest_message_at=latest_message_at,
            ),
        )
        with self._lock:
            self._state = SnapshotState(
                loaded,
                self._state.revision + 1,
                max_age_days,
                refreshed_at,
                latest_message_at,
            )
            return self._state

    def load_cached(self) -> SnapshotState:
        payload = self.store.get_mail_snapshot(str(self.profile.resolve()))
        if payload is None:
            return self.state
        cached = _decode_snapshot_state(payload)
        loaded = tuple(message for message in cached.messages if self._include_message(message))
        latest_message_at = cached.latest_message_at or _latest_message_datetime(loaded)
        with self._lock:
            self._state = SnapshotState(
                loaded,
                self._state.revision + 1,
                cached.max_age_days,
                cached.refreshed_at,
                latest_message_at,
            )
            return self._state

    def classify(self, rules: tuple[PersonalRule, ...]) -> tuple[ClassifiedMessage, ...]:
        return tuple(classify_message(message, rules) for message in self.state.messages)

    def full_message(self, header_message_id: str) -> MailMessage:
        message = next(
            (item for item in self.state.messages if item.header_message_id == header_message_id),
            None,
        )
        if message is None:
            raise KeyError(header_message_id)
        if message.mbox_path is None:
            return message
        if message.body_complete:
            return message
        try:
            body = load_message_body(message.mbox_path, message.header_message_id)
        except (OSError, KeyError, ValueError):
            return message
        return replace(
            message,
            body=body,
            body_complete=True,
            body_is_bare_link=is_bare_link_body(body),
        )

    def full_messages(self, header_message_ids: Iterable[str]) -> tuple[MailMessage, ...]:
        requested = tuple(header_message_ids)
        by_id = {message.header_message_id: message for message in self.state.messages}
        missing = [message_id for message_id in requested if message_id not in by_id]
        if missing:
            raise KeyError(missing[0])

        hydrated: dict[str, MailMessage] = {}
        by_mbox: dict[Path, list[MailMessage]] = {}
        for message_id in requested:
            message = by_id[message_id]
            if message.body_complete or message.mbox_path is None:
                hydrated[message_id] = message
            else:
                by_mbox.setdefault(message.mbox_path, []).append(message)

        for mbox_path, messages in by_mbox.items():
            try:
                bodies = load_message_bodies(
                    mbox_path,
                    (message.header_message_id for message in messages),
                )
            except (OSError, ValueError):
                bodies = {}
            for message in messages:
                body = bodies.get(message.header_message_id)
                hydrated[message.header_message_id] = (
                    message
                    if body is None
                    else replace(
                        message,
                        body=body,
                        body_complete=True,
                        body_is_bare_link=is_bare_link_body(body),
                    )
                )

        return tuple(hydrated[message_id] for message_id in requested)

    def visible(
        self,
        rules: tuple[PersonalRule, ...],
        *,
        view: str = "unread",
        max_age_days: int | None = None,
        now: datetime | None = None,
        sender_filter: str | None = None,
        domain_filter: str | None = None,
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
        for message in self.state.messages:
            sender = (message.sender or "").strip().lower()
            domain = sender.rsplit("@", 1)[1] if "@" in sender else ""
            if sender_filter and sender != sender_filter.strip().lower():
                continue
            if domain_filter and domain != domain_filter.strip().lower():
                continue
            message_date = message_datetime(message)
            if cutoff is not None and (message_date is None or message_date < cutoff):
                continue
            is_read = thunderbird_read(message) or message.header_message_id in app_read
            if view == "unread" and is_read:
                continue
            classified = classify_message(message, rules)
            grouped[classified.triage.priority].append(classified)
        for messages in grouped.values():
            messages.sort(
                key=lambda item: (
                    message_datetime(item.message) or datetime.min.replace(tzinfo=timezone.utc)
                ),
                reverse=True,
            )
        return {priority: tuple(grouped[priority]) for priority in PRIORITY_ORDER}

    def volume_stats(
        self,
        *,
        max_age_days: int,
        now: datetime | None = None,
    ) -> tuple[tuple[VolumeStat, ...], tuple[VolumeStat, ...]]:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        cutoff = current.astimezone(timezone.utc) - timedelta(days=max_age_days)
        app_read = self.store.read_ids()
        rows = []
        for message in self.state.messages:
            date = message_datetime(message)
            if date is None or date < cutoff:
                continue
            sender = (message.sender or "").strip().lower() or "(unknown)"
            domain = sender.rsplit("@", 1)[1] if "@" in sender else "(no domain)"
            unread = not (thunderbird_read(message) or message.header_message_id in app_read)
            rows.append((sender, domain, unread, date))
        total = len(rows)

        def aggregate(position: int) -> tuple[VolumeStat, ...]:
            grouped: dict[str, list[tuple[bool, datetime]]] = {}
            for row in rows:
                grouped.setdefault(row[position], []).append((row[2], row[3]))
            stats = [
                VolumeStat(
                    value=value,
                    count=len(items),
                    unread_count=sum(unread for unread, _date in items),
                    share=len(items) / total if total else 0.0,
                    most_recent=max(date for _unread, date in items),
                )
                for value, items in grouped.items()
            ]
            return tuple(sorted(stats, key=lambda item: (-item.count, item.value)))

        return aggregate(0), aggregate(1)

    def mark_read(self, header_message_id: str) -> None:
        if header_message_id not in {item.header_message_id for item in self.state.messages}:
            raise KeyError(header_message_id)
        self.store.mark_read(header_message_id)

    def remove_message(self, header_message_id: str) -> None:
        self.remove_messages((header_message_id,))

    def remove_messages(self, header_message_ids: Iterable[str]) -> None:
        selected = set(header_message_ids)
        with self._lock:
            max_age_days = self._state.max_age_days
            refreshed_at = self._state.refreshed_at
            remaining = tuple(
                item for item in self._state.messages if item.header_message_id not in selected
            )
            if len(remaining) == len(self._state.messages):
                raise KeyError(next(iter(selected), ""))
            self._state = SnapshotState(
                remaining,
                self._state.revision + 1,
                max_age_days,
                refreshed_at,
                _latest_message_datetime(remaining),
            )
        self.store.put_mail_snapshot(
            str(self.profile.resolve()),
            _encode_snapshot(
                remaining,
                max_age_days=max_age_days,
                refreshed_at=refreshed_at,
                latest_message_at=_latest_message_datetime(remaining),
            ),
        )


def _snapshot_covers_window(available_days: int | None, requested_days: int) -> bool:
    if available_days is None:
        return True
    return available_days >= requested_days


def _latest_message_datetime(messages: tuple[MailMessage, ...]) -> datetime | None:
    dates = [date for message in messages if (date := message_datetime(message)) is not None]
    return max(dates) if dates else None


def _encode_snapshot(
    messages: tuple[MailMessage, ...],
    *,
    max_age_days: int | None = None,
    refreshed_at: datetime | None = None,
    latest_message_at: datetime | None = None,
) -> str:
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
                "local_read": message.local_read,
                "read_state_source": message.read_state_source,
                "body_complete": message.body_complete,
                "body_is_bare_link": message.body_is_bare_link,
                "metadata": None
                if metadata is None
                else {
                    "header_message_id": metadata.header_message_id,
                    "message_key": metadata.message_key,
                    "folder_id": metadata.folder_id,
                    "conversation_id": metadata.conversation_id,
                    "date": metadata.date,
                    "sender_id": metadata.sender_id,
                    "recipient_ids": metadata.recipient_ids,
                    "sender": None
                    if metadata.sender is None
                    else {
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
    return json.dumps(
        {
            "max_age_days": max_age_days,
            "refreshed_at": refreshed_at.isoformat() if refreshed_at else None,
            "latest_message_at": latest_message_at.isoformat() if latest_message_at else None,
            "message_count": len(messages),
            "messages": encoded,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _decode_snapshot(payload: str) -> tuple[MailMessage, ...]:
    return _decode_snapshot_state(payload).messages


@dataclass(frozen=True)
class DecodedSnapshot:
    messages: tuple[MailMessage, ...]
    max_age_days: int | None
    refreshed_at: datetime | None
    latest_message_at: datetime | None


def _parse_snapshot_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decode_snapshot_state(payload: str) -> DecodedSnapshot:
    data = json.loads(payload)
    if isinstance(data, list):
        raw_messages = data
        # Legacy snapshots predate window metadata. They may be full or
        # windowed, so treat coverage as unknown to force a fresh refresh for
        # any explicit window while still rendering the cached rows immediately.
        max_age_days = 0
        refreshed_at = None
        latest_message_at = None
    elif isinstance(data, dict):
        raw_messages = data.get("messages", [])
        raw_max_age_days = data.get("max_age_days")
        max_age_days = int(raw_max_age_days) if raw_max_age_days is not None else None
        refreshed_at = _parse_snapshot_datetime(data.get("refreshed_at"))
        latest_message_at = _parse_snapshot_datetime(data.get("latest_message_at"))
    else:
        raise ValueError("Snapshot payload must be a list or object")
    messages = []
    for raw in raw_messages:
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
        messages.append(
            MailMessage(
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
                local_read=bool(raw.get("local_read", False)),
                read_state_source=str(raw.get("read_state_source", "mbox")),
                body_complete=bool(raw.get("body_complete", True)),
                body_is_bare_link=raw.get("body_is_bare_link"),
            )
        )
    return DecodedSnapshot(
        messages=tuple(messages),
        max_age_days=max_age_days,
        refreshed_at=refreshed_at,
        latest_message_at=latest_message_at,
    )
