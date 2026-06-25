"""Small local SQLite index for processed MAIL-00 messages."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
from typing import Iterable

from .thunderbird import MailMessage
from .triage import TriageResult


DEFAULT_INDEX_PATH = Path.home() / ".local" / "share" / "mail_lib" / "index.db"


@dataclass(frozen=True)
class IndexedMessage:
    header_message_id: str
    priority: str


class MailIndex:
    def __init__(self, path: str | Path = DEFAULT_INDEX_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MailIndex":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _setup(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_messages (
                headerMessageID TEXT PRIMARY KEY,
                message_date TEXT,
                priority TEXT,
                reason TEXT,
                matched_rules TEXT,
                processed_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_run_ts REAL NOT NULL
            );
            """
        )
        self._conn.commit()

    def processed_ids(self) -> set[str]:
        rows = self._conn.execute("SELECT headerMessageID FROM processed_messages").fetchall()
        return {str(row["headerMessageID"]) for row in rows}

    def new_messages(self, messages: Iterable[MailMessage]) -> list[MailMessage]:
        seen = self.processed_ids()
        return [message for message in messages if message.header_message_id not in seen]

    def record_results(
        self,
        messages: Iterable[MailMessage],
        results: Iterable[TriageResult],
        *,
        processed_at: float | None = None,
    ) -> None:
        by_id = {message.header_message_id: message for message in messages}
        timestamp = time.time() if processed_at is None else processed_at
        for result in results:
            message = by_id.get(result.header_message_id)
            self._conn.execute(
                """
                INSERT OR REPLACE INTO processed_messages
                    (headerMessageID, message_date, priority, reason, matched_rules, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.header_message_id,
                    message.date if message else None,
                    result.priority.value,
                    result.reason,
                    ",".join(result.matched_rules),
                    timestamp,
                ),
            )
        self._conn.execute(
            "INSERT OR REPLACE INTO runs (id, last_run_ts) VALUES (1, ?)",
            (timestamp,),
        )
        self._conn.commit()

    def get_priority(self, header_message_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT priority FROM processed_messages WHERE headerMessageID = ?",
            (header_message_id,),
        ).fetchone()
        return str(row["priority"]) if row else None
