from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from llm_inspector_ui.state.models import ChatSession, ChatTurn, RunArtifact, WorkbenchProfile


class SessionStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    meta_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS turns (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    meta_json TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_turns_session_created
                ON turns(session_id, created_at);

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    assistant_turn_id TEXT,
                    created_at TEXT NOT NULL,
                    engine_id TEXT NOT NULL,
                    model_id TEXT,
                    augmenter_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ok',
                    user_text TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    engine_metrics_json TEXT NOT NULL,
                    settings_json TEXT NOT NULL,
                    error TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                    FOREIGN KEY(turn_id) REFERENCES turns(turn_id)
                );

                CREATE INDEX IF NOT EXISTS idx_runs_session_created
                ON runs(session_id, created_at);

                CREATE TABLE IF NOT EXISTS profiles (
                    profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

            run_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "status" not in run_columns:
                conn.execute("ALTER TABLE runs ADD COLUMN status TEXT NOT NULL DEFAULT 'ok'")

    def _json_default(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "to_dict") and callable(value.to_dict):
            return value.to_dict()
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return str(value)

    def _dumps(self, value: Any) -> str:
        return json.dumps(value, default=self._json_default, ensure_ascii=False)

    def _loads(self, value: str | None, fallback: Any) -> Any:
        if not value:
            return fallback
        try:
            return json.loads(value)
        except Exception:
            return fallback

    def create_session(
        self, title: Optional[str] = None, *, meta: Optional[dict[str, Any]] = None
    ) -> ChatSession:
        now = datetime.now(timezone.utc)
        session = ChatSession(
            session_id=str(uuid4()),
            title=title or "New session",
            created_at=now,
            updated_at=now,
            meta=meta or {},
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, title, created_at, updated_at, meta_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.title,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                    self._dumps(session.meta),
                ),
            )
        return session

    def touch_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (datetime.now(timezone.utc).isoformat(), session_id),
            )

    def list_sessions(self) -> list[ChatSession]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, title, created_at, updated_at, meta_json
                FROM sessions
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, title, created_at, updated_at, meta_json
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return self._row_to_session(row) if row else None

    def add_turn(
        self,
        session_id: str,
        role: str,
        text: str,
        meta: Optional[dict[str, Any]] = None,
    ) -> ChatTurn:
        turn = ChatTurn(
            turn_id=str(uuid4()),
            session_id=session_id,
            role=role,
            text=text,
            created_at=datetime.now(timezone.utc),
            meta=meta or {},
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO turns (turn_id, session_id, role, text, created_at, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    turn.turn_id,
                    turn.session_id,
                    turn.role,
                    turn.text,
                    turn.created_at.isoformat(),
                    self._dumps(turn.meta),
                ),
            )
        self.touch_session(session_id)
        return turn

    def list_turns(self, session_id: str) -> list[ChatTurn]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT turn_id, session_id, role, text, created_at, meta_json
                FROM turns
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_turn(row) for row in rows]

    def save_run(self, run: RunArtifact) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, session_id, turn_id, assistant_turn_id, created_at,
                    engine_id, model_id, augmenter_id, mode, status, user_text, prompt,
                    response_text, trace_json, engine_metrics_json, settings_json, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.session_id,
                    run.turn_id,
                    run.assistant_turn_id,
                    run.created_at.isoformat(),
                    run.engine_id,
                    run.model_id,
                    run.augmenter_id,
                    run.mode,
                    run.status,
                    run.user_text,
                    run.prompt,
                    run.response_text,
                    self._dumps(run.trace),
                    self._dumps(run.engine_metrics),
                    self._dumps(run.settings),
                    run.error,
                ),
            )
        self.touch_session(run.session_id)

    def list_runs(self, session_id: str) -> list[RunArtifact]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM runs
                WHERE session_id = ?
                ORDER BY created_at DESC
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_run(self, run_id: str) -> Optional[RunArtifact]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def save_profile(self, profile: WorkbenchProfile) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO profiles (profile_id, name, payload_json)
                VALUES (?, ?, ?)
                """,
                (profile.profile_id, profile.name, self._dumps(asdict(profile))),
            )

    def list_profiles(self) -> list[WorkbenchProfile]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT profile_id, name, payload_json
                FROM profiles
                ORDER BY name ASC
                """
            ).fetchall()
        profiles: list[WorkbenchProfile] = []
        for row in rows:
            payload = self._loads(row["payload_json"], {})
            profiles.append(WorkbenchProfile(**payload))
        return profiles

    def get_profile(self, profile_id: str) -> Optional[WorkbenchProfile]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT profile_id, name, payload_json
                FROM profiles
                WHERE profile_id = ?
                """,
                (profile_id,),
            ).fetchone()
        if not row:
            return None
        payload = self._loads(row["payload_json"], {})
        return WorkbenchProfile(**payload)

    def delete_profile(self, profile_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM profiles WHERE profile_id = ?",
                (profile_id,),
            )

    def _row_to_session(self, row: sqlite3.Row) -> ChatSession:
        return ChatSession(
            session_id=row["session_id"],
            title=row["title"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            meta=self._loads(row["meta_json"], {}),
        )

    def _row_to_turn(self, row: sqlite3.Row) -> ChatTurn:
        return ChatTurn(
            turn_id=row["turn_id"],
            session_id=row["session_id"],
            role=row["role"],
            text=row["text"],
            created_at=datetime.fromisoformat(row["created_at"]),
            meta=self._loads(row["meta_json"], {}),
        )

    def _row_to_run(self, row: sqlite3.Row) -> RunArtifact:
        row_keys = set(row.keys())
        return RunArtifact(
            run_id=row["run_id"],
            session_id=row["session_id"],
            turn_id=row["turn_id"],
            assistant_turn_id=row["assistant_turn_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            engine_id=row["engine_id"],
            model_id=row["model_id"],
            augmenter_id=row["augmenter_id"],
            mode=row["mode"],
            status=row["status"] if "status" in row_keys else "ok",
            user_text=row["user_text"],
            prompt=row["prompt"],
            response_text=row["response_text"],
            trace=self._loads(row["trace_json"], None),
            engine_metrics=self._loads(row["engine_metrics_json"], {}),
            settings=self._loads(row["settings_json"], {}),
            error=row["error"],
        )
