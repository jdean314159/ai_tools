"""App-owned persistence for the local mail assistant."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import time


DEFAULT_STORE_PATH = Path.home() / ".local" / "share" / "mail_assistant" / "assistant.db"


class AssistantStore:
    """Small SQLite store using one connection per operation."""

    def __init__(self, path: str | Path = DEFAULT_STORE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=3.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=3000")
        return connection

    def _setup(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS read_state (
                    header_message_id TEXT PRIMARY KEY,
                    read_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS section_summary_cache (
                    section_key TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (section_key, model, prompt_version)
                );
                CREATE TABLE IF NOT EXISTS mail_snapshot_cache (
                    profile TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            connection.commit()

    def get_mail_snapshot(self, profile: str) -> str | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM mail_snapshot_cache WHERE profile = ?", (profile,)
            ).fetchone()
        return str(row["payload"]) if row else None

    def put_mail_snapshot(self, profile: str, payload: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO mail_snapshot_cache (profile, payload, created_at) "
                "VALUES (?, ?, ?)",
                (profile, payload, time.time()),
            )
            connection.commit()

    def mark_read(self, header_message_id: str, *, read_at: float | None = None) -> None:
        timestamp = time.time() if read_at is None else read_at
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO read_state (header_message_id, read_at) VALUES (?, ?)",
                (header_message_id, timestamp),
            )
            connection.commit()

    def read_ids(self) -> set[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT header_message_id FROM read_state").fetchall()
        return {str(row["header_message_id"]) for row in rows}

    def get_summary(self, section_key: str, model: str, prompt_version: str) -> str | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT summary FROM section_summary_cache "
                "WHERE section_key = ? AND model = ? AND prompt_version = ?",
                (section_key, model, prompt_version),
            ).fetchone()
        return str(row["summary"]) if row else None

    def put_summary(
        self,
        section_key: str,
        model: str,
        prompt_version: str,
        summary: str,
        *,
        created_at: float | None = None,
    ) -> None:
        timestamp = time.time() if created_at is None else created_at
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO section_summary_cache "
                "(section_key, model, prompt_version, summary, created_at) VALUES (?, ?, ?, ?, ?)",
                (section_key, model, prompt_version, summary, timestamp),
            )
            connection.commit()
