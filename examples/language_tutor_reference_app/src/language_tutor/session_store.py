"""
Session Persistence for Language Tutor

Lightweight SQLite store for per-session statistics and historical
weakness analysis. Sits alongside Engram's data directory and feeds
the planner prompt with concrete historical data.

Adapted from spanish_tutor/services/session_service.py.

Author: Jeff
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class SessionStore:
    """
    Persists session statistics across restarts.

    Stores to data/memory/<language>_sessions.db — separate from Engram's
    own databases so there's no schema conflict.

    Used by TutorSession to:
      - Record session results at end_session()
      - Supply historical weakness data to the planning prompt
      - Provide user-facing progress stats
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id          TEXT PRIMARY KEY,
                    language            TEXT NOT NULL,
                    started_at          TIMESTAMP,
                    completed_at        TIMESTAMP,
                    drill_focus         TEXT,
                    exchanges           INTEGER DEFAULT 0,
                    corrections_made    INTEGER DEFAULT 0,
                    vocab_learned       INTEGER DEFAULT 0,
                    drill_accuracy      REAL DEFAULT 0.0,
                    duration_minutes    REAL DEFAULT 0.0,
                    summary             TEXT
                );

                CREATE TABLE IF NOT EXISTS mistakes_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id      TEXT NOT NULL,
                    language        TEXT NOT NULL,
                    error_type      TEXT,
                    incorrect       TEXT,
                    correct         TEXT,
                    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS vocab_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    language    TEXT NOT NULL,
                    word        TEXT NOT NULL,
                    translation TEXT,
                    timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS vocabulary_mastery (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    language          TEXT NOT NULL,
                    word              TEXT NOT NULL,
                    translation       TEXT NOT NULL,
                    mastery_level     INTEGER DEFAULT 0,
                    times_correct     INTEGER DEFAULT 0,
                    times_incorrect   INTEGER DEFAULT 0,
                    last_reviewed     TIMESTAMP,
                    next_review       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(language, word)
                );
            """)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self, session_id: str, language: str, drill_focus: str = ""):
        """Record session start."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sessions
                    (session_id, language, started_at, drill_focus)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, language, datetime.now().isoformat(), drill_focus),
            )

    def complete_session(
        self,
        session_id: str,
        *,
        exchanges: int = 0,
        corrections_made: int = 0,
        vocab_learned: int = 0,
        drill_accuracy: float = 0.0,
        duration_minutes: float = 0.0,
        summary: str = "",
    ):
        """Record session completion statistics."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE sessions SET
                    completed_at     = ?,
                    exchanges        = ?,
                    corrections_made = ?,
                    vocab_learned    = ?,
                    drill_accuracy   = ?,
                    duration_minutes = ?,
                    summary          = ?
                WHERE session_id = ?
                """,
                (
                    datetime.now().isoformat(),
                    exchanges,
                    corrections_made,
                    vocab_learned,
                    drill_accuracy,
                    round(duration_minutes, 1),
                    summary[:2000],
                    session_id,
                ),
            )

    def log_mistake(
        self,
        session_id: str,
        language: str,
        incorrect: str,
        correct: str,
        error_type: str = "",
    ):
        """Log a single correction/mistake."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO mistakes_log
                    (session_id, language, error_type, incorrect, correct)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, language, error_type[:100], incorrect[:300], correct[:300]),
            )

    def log_vocab(
        self,
        session_id: str,
        language: str,
        word: str,
        translation: str = "",
    ):
        """Log a vocabulary item introduced this session."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO vocab_log
                    (session_id, language, word, translation)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, language, word[:100], translation[:200]),
            )

    # ------------------------------------------------------------------
    # Vocabulary mastery (spaced repetition — SM-2)
    # ------------------------------------------------------------------

    # SM-2 review intervals in days, indexed by mastery_level 0-5
    _SM2_INTERVALS = [1, 3, 7, 14, 30, 90]

    def record_vocab_result(
        self,
        language: str,
        word: str,
        translation: str,
        correct: bool,
    ) -> None:
        """Update vocabulary mastery after a spaced-repetition review.

        Uses a simplified SM-2 schedule:
          - Correct answer → mastery_level += 1 (capped at 5)
          - Incorrect answer → mastery_level reset to 0
        next_review is set to now + interval[mastery_level].
        """
        from datetime import datetime, timedelta

        now = datetime.utcnow().isoformat()

        with self._conn() as conn:
            # Upsert the word
            conn.execute(
                """
                INSERT INTO vocabulary_mastery
                    (language, word, translation, mastery_level,
                     times_correct, times_incorrect, last_reviewed, next_review)
                VALUES (?, ?, ?, 0, 0, 0, ?, ?)
                ON CONFLICT(language, word) DO NOTHING
                """,
                (language, word[:100], translation[:200], now, now),
            )
            # Fetch current mastery level
            row = conn.execute(
                "SELECT mastery_level FROM vocabulary_mastery WHERE language=? AND word=?",
                (language, word),
            ).fetchone()
            if row is None:
                return

            current_level = row["mastery_level"]
            if correct:
                new_level = min(5, current_level + 1)
            else:
                new_level = 0

            interval_days = self._SM2_INTERVALS[new_level]
            next_review = (datetime.utcnow() + timedelta(days=interval_days)).isoformat()

            if correct:
                conn.execute(
                    """
                    UPDATE vocabulary_mastery
                    SET mastery_level=?, times_correct=times_correct+1,
                        last_reviewed=?, next_review=?
                    WHERE language=? AND word=?
                    """,
                    (new_level, now, next_review, language, word),
                )
            else:
                conn.execute(
                    """
                    UPDATE vocabulary_mastery
                    SET mastery_level=?, times_incorrect=times_incorrect+1,
                        last_reviewed=?, next_review=?
                    WHERE language=? AND word=?
                    """,
                    (new_level, now, next_review, language, word),
                )

    def seed_vocab_from_log(self, language: str) -> int:
        """Seed vocabulary_mastery from vocab_log for words not yet tracked.

        Call this when starting a review drill to ensure words encountered
        in conversation are available for spaced repetition even if they
        haven't been reviewed explicitly before.

        Returns count of rows inserted.
        """
        with self._conn() as conn:
            result = conn.execute(
                """
                INSERT OR IGNORE INTO vocabulary_mastery
                    (language, word, translation)
                SELECT DISTINCT language, word, COALESCE(translation, '')
                FROM vocab_log
                WHERE language = ?
                  AND word != ''
                """,
                (language,),
            )
            return result.rowcount

    def get_vocab_due(self, language: str, limit: int = 10):
        """Return vocabulary words due for review, oldest-due first.

        Returns list of dicts: {word, translation, mastery_level,
        times_correct, times_incorrect, days_overdue}.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    word, translation, mastery_level,
                    times_correct, times_incorrect,
                    CAST(
                        (julianday('now') - julianday(next_review))
                        AS INTEGER
                    ) AS days_overdue
                FROM vocabulary_mastery
                WHERE language = ?
                  AND next_review <= datetime('now')
                ORDER BY next_review ASC
                LIMIT ?
                """,
                (language, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_vocab_stats(self, language: str) -> dict:
        """Return summary statistics for vocabulary mastery."""
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM vocabulary_mastery WHERE language=?",
                (language,),
            ).fetchone()["c"]
            due = conn.execute(
                """
                SELECT COUNT(*) AS c FROM vocabulary_mastery
                WHERE language=? AND next_review <= datetime('now')
                """,
                (language,),
            ).fetchone()["c"]
            mastered = conn.execute(
                """
                SELECT COUNT(*) AS c FROM vocabulary_mastery
                WHERE language=? AND mastery_level >= 4
                """,
                (language,),
            ).fetchone()["c"]
        return {"total": total, "due_for_review": due, "mastered": mastered}

    # ------------------------------------------------------------------
    # Weakness analysis (feeds the planner prompt)
    # ------------------------------------------------------------------

    def get_weaknesses(self, language: str, days_back: int = 30, limit: int = 5) -> List[Dict]:
        """
        Return the most frequent mistake types over recent sessions.

        Used by TutorSession._build_planning_prompt() to tell the planner
        what the student most needs to work on.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    error_type,
                    COUNT(*) AS cnt,
                    GROUP_CONCAT(incorrect, ' | ') AS examples
                FROM mistakes_log
                WHERE language = ?
                  AND timestamp > datetime('now', ?)
                GROUP BY error_type
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (language, f"-{days_back} days", limit),
            ).fetchall()
        return [
            {
                "error_type": row["error_type"] or "grammar",
                "count": row["cnt"],
                "examples": (row["examples"] or "").split(" | ")[:3],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Progress stats
    # ------------------------------------------------------------------

    def get_user_stats(self, language: str) -> Dict[str, Any]:
        """Return aggregate progress statistics for the user."""
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM sessions WHERE language=? AND completed_at IS NOT NULL",
                (language,),
            ).fetchone()["c"]

            avg_corrections = (
                conn.execute(
                    """
                SELECT AVG(corrections_made) AS avg
                FROM sessions
                WHERE language=? AND completed_at IS NOT NULL
                """,
                    (language,),
                ).fetchone()["avg"]
                or 0.0
            )

            recent = conn.execute(
                """
                SELECT session_id, started_at, exchanges, corrections_made,
                       vocab_learned, drill_accuracy, duration_minutes
                FROM sessions
                WHERE language=? AND completed_at IS NOT NULL
                ORDER BY started_at DESC
                LIMIT 7
                """,
                (language,),
            ).fetchall()

        return {
            "total_sessions": total,
            "avg_corrections_per_session": round(avg_corrections, 1),
            "recent_sessions": [dict(r) for r in recent],
        }

    def get_session_history(self, language: str, limit: int = 10) -> List[Dict]:
        """Return recent completed session summaries."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT session_id, started_at, completed_at, drill_focus,
                       exchanges, corrections_made, vocab_learned,
                       drill_accuracy, duration_minutes, summary
                FROM sessions
                WHERE language=? AND completed_at IS NOT NULL
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (language, limit),
            ).fetchall()
        return [dict(r) for r in rows]
