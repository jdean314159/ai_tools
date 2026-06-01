from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class TutorStore:
    """Small SQLite store for history, mistakes, and spaced repetition."""

    _INTERVALS = [1, 3, 7, 14, 30, 90]

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    language TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    exchanges INTEGER DEFAULT 0,
                    corrections INTEGER DEFAULT 0,
                    vocab_count INTEGER DEFAULT 0,
                    drill_accuracy REAL DEFAULT 0,
                    summary TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS mistakes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    language TEXT,
                    error TEXT,
                    correction TEXT,
                    error_type TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS vocab (
                    language TEXT,
                    word TEXT,
                    translation TEXT,
                    mastery INTEGER DEFAULT 0,
                    correct INTEGER DEFAULT 0,
                    incorrect INTEGER DEFAULT 0,
                    next_review TEXT,
                    PRIMARY KEY(language, word)
                );
                """
            )

    def start_session(self, session_id: str, language: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, language, started_at) VALUES (?, ?, ?)",
                (session_id, language, datetime.now(UTC).isoformat()),
            )

    def complete_session(self, session_id: str, *, exchanges: int, corrections: int, vocab_count: int, drill_accuracy: float, summary: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE sessions SET completed_at=?, exchanges=?, corrections=?,
                    vocab_count=?, drill_accuracy=?, summary=?
                WHERE session_id=?
                """,
                (datetime.now(UTC).isoformat(), exchanges, corrections, vocab_count, drill_accuracy, summary, session_id),
            )

    def log_mistake(self, session_id: str, language: str, error: str, correction: str, error_type: str = "grammar") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO mistakes(session_id, language, error, correction, error_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, language, error[:200], correction[:200], error_type[:80], datetime.now(UTC).isoformat()),
            )

    def add_vocab(self, language: str, word: str, translation: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO vocab(language, word, translation, next_review)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(language, word) DO UPDATE SET
                    translation=excluded.translation
                """,
                (language, word[:100], translation[:200], now),
            )

    def record_vocab_result(self, language: str, word: str, translation: str, correct: bool) -> None:
        self.add_vocab(language, word, translation)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mastery FROM vocab WHERE language=? AND word=?",
                (language, word),
            ).fetchone()
            mastery = int(row["mastery"]) if row else 0
            mastery = min(5, mastery + 1) if correct else 0
            next_review = (datetime.now(UTC) + timedelta(days=self._INTERVALS[mastery])).isoformat()
            if correct:
                conn.execute(
                    "UPDATE vocab SET mastery=?, correct=correct+1, next_review=? WHERE language=? AND word=?",
                    (mastery, next_review, language, word),
                )
            else:
                conn.execute(
                    "UPDATE vocab SET mastery=?, incorrect=incorrect+1, next_review=? WHERE language=? AND word=?",
                    (mastery, next_review, language, word),
                )

    def due_vocab(self, language: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT word, translation, mastery FROM vocab
                WHERE language=? AND next_review<=?
                ORDER BY mastery ASC, word ASC
                LIMIT ?
                """,
                (language, datetime.now(UTC).isoformat(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def history(self, language: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE language=? ORDER BY started_at DESC LIMIT ?",
                (language, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self, language: str) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT count(*) AS sessions, sum(exchanges) AS exchanges,
                    sum(corrections) AS corrections, sum(vocab_count) AS vocab_count,
                    avg(drill_accuracy) AS drill_accuracy
                FROM sessions WHERE language=?
                """,
                (language,),
            ).fetchone()
            mistakes = conn.execute(
                """
                SELECT error_type, count(*) AS count FROM mistakes
                WHERE language=? GROUP BY error_type ORDER BY count DESC
                """,
                (language,),
            ).fetchall()
        result = dict(row) if row else {}
        result["weaknesses"] = [dict(item) for item in mistakes]
        return result
