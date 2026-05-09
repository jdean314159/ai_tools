"""
engram/memory/procedural.py

ProceduralMemory — Layer 6 of the Engram memory stack.

Stores reusable "skills": structured procedural knowledge extracted from
recurring patterns in episodic and semantic memory.  Each skill captures:

    - what triggers it (a short trigger phrase)
    - when to apply it (guidance text)
    - how to execute it (ordered steps)
    - evidence it works (supporting episodes, examples)
    - how confident we are it generalises

Skills are retrieved by a hybrid matcher that combines:
    - FTS5 BM25 lexical scoring (fast, no model required)
    - Cosine similarity over stored embedding vectors (numpy, no ChromaDB)

The two scores are linearly blended (default: 50/50) and the top-k results
are returned as SkillMatch objects carrying per-source scores.

Storage follows the exact pattern of SemanticMemory:
    - SQLite WAL mode
    - Single writer connection protected by threading.RLock
    - Per-thread reader connections via threading.local
    - FTS5 virtual table kept in sync via INSERT/DELETE/UPDATE triggers
    - Embeddings stored as raw BLOB (numpy float32 .tobytes())

This module is self-contained.  Phase B will wire extraction; Phase C will
integrate with ProjectMemory / UnifiedRetriever.

Author: Jeffrey Dean
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional numpy — required for embedding storage and cosine similarity.
# If numpy is absent the layer still works in lexical-only mode.
# ---------------------------------------------------------------------------
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    np = None  # type: ignore
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_STMTS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA cache_size=-8000",
    """
    CREATE TABLE IF NOT EXISTS skills (
        id                  TEXT PRIMARY KEY,
        name                TEXT NOT NULL,
        trigger             TEXT NOT NULL,
        when_to_use         TEXT NOT NULL DEFAULT '',
        steps               TEXT NOT NULL DEFAULT '[]',
        examples            TEXT NOT NULL DEFAULT '[]',
        support_episode_ids TEXT NOT NULL DEFAULT '[]',
        confidence          REAL NOT NULL DEFAULT 0.0,
        embedding           BLOB,
        embedding_dim       INTEGER,
        created_at          REAL NOT NULL,
        last_used_at        REAL,
        use_count           INTEGER NOT NULL DEFAULT 0,
        project_id          TEXT NOT NULL DEFAULT '',
        metadata            TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_skills_project    ON skills(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_skills_confidence ON skills(confidence DESC)",
    "CREATE INDEX IF NOT EXISTS idx_skills_created    ON skills(created_at DESC)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
        name,
        trigger,
        when_to_use,
        content='skills',
        content_rowid='rowid',
        tokenize='unicode61 remove_diacritics 1'
    )
    """,
    # FTS5 sync triggers — must be individual statements (bodies contain semicolons)
    """
    CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills BEGIN
        INSERT INTO skills_fts(rowid, name, trigger, when_to_use)
        VALUES (new.rowid, new.name, new.trigger, new.when_to_use);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills BEGIN
        INSERT INTO skills_fts(skills_fts, rowid, name, trigger, when_to_use)
        VALUES ('delete', old.rowid, old.name, old.trigger, old.when_to_use);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS skills_au AFTER UPDATE ON skills BEGIN
        INSERT INTO skills_fts(skills_fts, rowid, name, trigger, when_to_use)
        VALUES ('delete', old.rowid, old.name, old.trigger, old.when_to_use);
        INSERT INTO skills_fts(rowid, name, trigger, when_to_use)
        VALUES (new.rowid, new.name, new.trigger, new.when_to_use);
    END
    """,
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Skill:
    """One reusable procedural skill.

    Args:
        name:                Short, human-readable title.
        trigger:             Phrase that describes when this skill applies,
                             e.g. "when refactoring SQLite schema with WAL".
        steps:               Ordered list of procedure steps.
        when_to_use:         Longer guidance for the LLM / retriever.
        examples:            List of {input, output} dicts from source episodes.
        support_episode_ids: Episode IDs that provided evidence for this skill.
        confidence:          0.0–1.0 extraction confidence.
        embedding:           float32 numpy array for semantic matching, or None.
        project_id:          Scopes the skill to a project ('' = global).
        metadata:            Arbitrary caller-controlled metadata.
        skill_id:            Stable hash; auto-computed from name + trigger if None.
        created_at:          Unix timestamp; set on first store if None.
        last_used_at:        Unix timestamp; updated by record_use().
        use_count:           Incremented by record_use().
    """
    name: str
    trigger: str
    steps: List[str]
    when_to_use: str = ""
    examples: List[Dict[str, Any]] = field(default_factory=list)
    support_episode_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    embedding: Optional[Any] = None      # np.ndarray | None
    project_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    skill_id: Optional[str] = None
    created_at: Optional[float] = None
    last_used_at: Optional[float] = None
    use_count: int = 0

    def __post_init__(self) -> None:
        if self.skill_id is None:
            self.skill_id = _stable_id(self.name, self.trigger, self.project_id)
        if self.created_at is None:
            self.created_at = time.time()

    def to_prompt_text(self) -> str:
        """Format skill for injection into an LLM prompt."""
        lines = [f"## Skill: {self.name}"]
        if self.when_to_use:
            lines.append(f"**When to use:** {self.when_to_use}")
        lines.append("**Steps:**")
        for i, step in enumerate(self.steps, 1):
            lines.append(f"  {i}. {step}")
        if self.examples:
            lines.append("**Examples:**")
            for ex in self.examples[:2]:
                inp = ex.get("input", "")
                out = ex.get("output", "")
                if inp or out:
                    lines.append(f"  - Input: {inp}")
                    lines.append(f"    Output: {out}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable representation (no numpy, no bytes)."""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "trigger": self.trigger,
            "when_to_use": self.when_to_use,
            "steps": self.steps,
            "examples": self.examples,
            "support_episode_ids": self.support_episode_ids,
            "confidence": self.confidence,
            "project_id": self.project_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
            "has_embedding": self.embedding is not None,
        }


@dataclass
class SkillMatch:
    """A skill returned by match_skills(), with per-source scores."""
    skill: Skill
    score: float           # blended 0..1
    lexical_score: float   # 0..1 from FTS5 BM25
    semantic_score: float  # 0..1 from cosine similarity
    matched_via: str       # "lexical" | "semantic" | "hybrid"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _stable_id(name: str, trigger: str, project_id: str = "") -> str:
    key = f"{project_id}::{name}::{trigger}".lower().strip()
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def _safe_fts_query(text: str) -> str:
    """Strip FTS5 special characters and build a prefix-wildcard query."""
    import re
    tokens = re.sub(r'[^\w\s]', ' ', text).split()
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"*' for t in tokens[:12])


def _cosine(a: Any, b: Any) -> float:
    """Cosine similarity between two float32 numpy arrays."""
    if not _HAS_NUMPY:
        return 0.0
    try:
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            return 0.0
        return float(np.dot(a, b) / (na * nb))
    except Exception:
        return 0.0


def _emb_to_blob(emb: Any) -> Optional[bytes]:
    if emb is None or not _HAS_NUMPY:
        return None
    try:
        arr = np.asarray(emb, dtype=np.float32)
        return arr.tobytes()
    except Exception:
        return None


def _blob_to_emb(blob: Optional[bytes], dim: Optional[int]) -> Optional[Any]:
    if blob is None or not _HAS_NUMPY:
        return None
    try:
        arr = np.frombuffer(blob, dtype=np.float32)
        if dim and len(arr) != dim:
            return None
        return arr
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ProceduralMemory
# ---------------------------------------------------------------------------

class ProceduralMemory:
    """Layer 6 — procedural skill storage and hybrid retrieval.

    Args:
        db_path:      Path to the SQLite file (or directory; uses
                      ``procedural.db`` inside it).  None → ``:memory:``.
        project_type: Unused for now; accepted for interface symmetry
                      with other memory layers.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        project_type: Optional[Any] = None,
    ) -> None:
        if db_path is None:
            self._db_file = ":memory:"
        else:
            db_path = Path(db_path).expanduser().resolve(strict=False)
            if db_path.suffix in (".db", ".sqlite", ".sqlite3"):
                self._db_file = str(db_path)
                db_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                db_path.mkdir(parents=True, exist_ok=True)
                self._db_file = str(db_path / "procedural.db")

        self._lock = threading.RLock()
        self._local = threading.local()
        self._write_conn = self._open_conn()
        self._apply_schema(self._write_conn)

        logger.info("ProceduralMemory (SQLite) initialised at %s", self._db_file)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _open_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_file,
            check_same_thread=False,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA cache_size=-8000;")
        return conn

    def _read_conn(self) -> sqlite3.Connection:
        # :memory: databases are per-connection — always use the writer.
        if self._db_file == ":memory:":
            return self._write_conn
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._open_conn()
        return self._local.conn

    def _apply_schema(self, conn: sqlite3.Connection) -> None:
        for stmt in _SCHEMA_STMTS:
            stmt = stmt.strip()
            if stmt:
                try:
                    conn.execute(stmt)
                except sqlite3.Error as e:
                    if "already exists" not in str(e).lower():
                        raise
        conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_skill(self, skill: Skill) -> str:
        """Insert or replace a skill.  Returns skill_id."""
        with self._lock:
            self._write_conn.execute(
                """
                INSERT OR REPLACE INTO skills
                    (id, name, trigger, when_to_use, steps, examples,
                     support_episode_ids, confidence, embedding, embedding_dim,
                     created_at, last_used_at, use_count, project_id, metadata)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    skill.skill_id,
                    skill.name,
                    skill.trigger,
                    skill.when_to_use,
                    json.dumps(skill.steps),
                    json.dumps(skill.examples),
                    json.dumps(skill.support_episode_ids),
                    skill.confidence,
                    _emb_to_blob(skill.embedding),
                    int(len(skill.embedding)) if skill.embedding is not None else None,
                    skill.created_at,
                    skill.last_used_at,
                    skill.use_count,
                    skill.project_id,
                    json.dumps(skill.metadata),
                ),
            )
            self._write_conn.commit()
        return skill.skill_id  # type: ignore[return-value]

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Return one skill by ID, or None."""
        row = self._read_conn().execute(
            "SELECT * FROM skills WHERE id = ?", (skill_id,)
        ).fetchone()
        return _row_to_skill(row) if row else None

    def update_skill(self, skill_id: str, **fields: Any) -> bool:
        """Patch specific fields on a skill.  Returns True if found."""
        allowed = {
            "name", "trigger", "when_to_use", "steps", "examples",
            "support_episode_ids", "confidence", "project_id", "metadata",
            "embedding", "last_used_at", "use_count",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False

        # Serialize composite fields
        col_vals = []
        for k, v in updates.items():
            if k == "embedding":
                col_vals.append(("embedding", _emb_to_blob(v)))
                dim = int(len(v)) if v is not None else None
                col_vals.append(("embedding_dim", dim))
            elif k in ("steps", "examples", "support_episode_ids", "metadata"):
                col_vals.append((k, json.dumps(v)))
            else:
                col_vals.append((k, v))

        set_clause = ", ".join(f"{k} = ?" for k, _ in col_vals)
        values = [v for _, v in col_vals] + [skill_id]

        with self._lock:
            cur = self._write_conn.execute(
                f"UPDATE skills SET {set_clause} WHERE id = ?", values
            )
            self._write_conn.commit()
        return cur.rowcount > 0

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill.  Returns True if it existed."""
        with self._lock:
            cur = self._write_conn.execute(
                "DELETE FROM skills WHERE id = ?", (skill_id,)
            )
            self._write_conn.commit()
        return cur.rowcount > 0

    def list_skills(
        self,
        project_id: str = "",
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[Skill]:
        """List skills, optionally filtered by project and confidence."""
        rows = self._read_conn().execute(
            """
            SELECT * FROM skills
            WHERE project_id = ? AND confidence >= ?
            ORDER BY confidence DESC, created_at DESC
            LIMIT ?
            """,
            (project_id, min_confidence, limit),
        ).fetchall()
        return [_row_to_skill(r) for r in rows]

    def record_use(self, skill_id: str) -> None:
        """Increment use_count and update last_used_at."""
        with self._lock:
            self._write_conn.execute(
                """
                UPDATE skills
                SET use_count = use_count + 1, last_used_at = ?
                WHERE id = ?
                """,
                (time.time(), skill_id),
            )
            self._write_conn.commit()

    # ------------------------------------------------------------------
    # Hybrid retrieval
    # ------------------------------------------------------------------

    def match_skills(
        self,
        query: str,
        *,
        embedding: Optional[Any] = None,   # np.ndarray | None
        top_k: int = 5,
        lexical_weight: float = 0.5,
        min_confidence: float = 0.0,
        project_id: str = "",
    ) -> List[SkillMatch]:
        """Hybrid skill retrieval: FTS5 BM25 + cosine, linearly blended.

        If ``embedding`` is None, returns lexical-only results.
        If the FTS index has no hits, falls back to semantic-only (when
        embedding is provided) or returns an empty list.

        Args:
            query:          Natural-language task description.
            embedding:      Query embedding (numpy float32 array).  Pass the
                            result of EmbeddingService.embed(query).
            top_k:          Max results to return.
            lexical_weight: Weight for FTS5 score (0..1).  Remainder is
                            semantic.  Ignored when embedding is None.
            min_confidence: Filter — only return skills above this threshold.
            project_id:     Scope to a project ('' = global).

        Returns:
            List of SkillMatch, sorted by blended score descending.
        """
        lex_scores: Dict[str, float] = {}
        sem_scores: Dict[str, float] = {}
        all_ids: set = set()

        # --- FTS5 lexical pass ---
        fts_expr = _safe_fts_query(query)
        if fts_expr:
            try:
                # Step 1: get rowids + BM25 ranks from FTS index
                fts_rows = self._read_conn().execute(
                    "SELECT rowid, rank FROM skills_fts WHERE skills_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fts_expr, top_k * 4),
                ).fetchall()
                if fts_rows:
                    rowid_to_rank = {r["rowid"]: r["rank"] for r in fts_rows}
                    placeholders = ",".join("?" * len(rowid_to_rank))
                    # Step 2: filter by project / confidence using rowids
                    skill_rows = self._read_conn().execute(
                        f"""
                        SELECT rowid, id FROM skills
                        WHERE rowid IN ({placeholders})
                          AND project_id = ? AND confidence >= ?
                        """,
                        list(rowid_to_rank.keys()) + [project_id, min_confidence],
                    ).fetchall()
                    if skill_rows:
                        ranks = list(rowid_to_rank.values())
                        min_r, max_r = min(ranks), max(ranks)
                        span = max_r - min_r
                        for r in skill_rows:
                            if span < 1e-9:
                                # Single result or all same rank → full score
                                norm = 1.0
                            else:
                                # BM25 rank: more negative = better match
                                norm = (max_r - rowid_to_rank[r["rowid"]]) / span
                            lex_scores[r["id"]] = norm
                            all_ids.add(r["id"])
            except sqlite3.Error as e:
                logger.debug("ProceduralMemory FTS error: %s", e)

        # --- Cosine semantic pass ---
        if embedding is not None and _HAS_NUMPY:
            try:
                rows = self._read_conn().execute(
                    """
                    SELECT id, embedding, embedding_dim
                    FROM skills
                    WHERE project_id = ? AND confidence >= ? AND embedding IS NOT NULL
                    """,
                    (project_id, min_confidence),
                ).fetchall()
                for r in rows:
                    emb = _blob_to_emb(r["embedding"], r["embedding_dim"])
                    if emb is None:
                        continue
                    try:
                        query_arr = np.asarray(embedding, dtype=np.float32)
                    except Exception:
                        break
                    if query_arr.shape != emb.shape:
                        continue
                    sim = _cosine(query_arr, emb)
                    sim_clipped = max(0.0, min(1.0, (sim + 1.0) / 2.0))  # −1..1 → 0..1
                    sem_scores[r["id"]] = sim_clipped
                    all_ids.add(r["id"])
            except sqlite3.Error as e:
                logger.debug("ProceduralMemory cosine pass error: %s", e)

        if not all_ids:
            return []

        # --- Blend scores ---
        sem_w = (1.0 - lexical_weight) if embedding is not None else 0.0
        lex_w = lexical_weight if embedding is not None else 1.0

        blended: Dict[str, float] = {}
        for sid in all_ids:
            lex = lex_scores.get(sid, 0.0)
            sem = sem_scores.get(sid, 0.0)
            blended[sid] = lex_w * lex + sem_w * sem

        top_ids = sorted(blended, key=lambda x: blended[x], reverse=True)[: top_k * 2]

        if not top_ids:
            return []

        placeholders = ",".join("?" * len(top_ids))
        rows = self._read_conn().execute(
            f"SELECT * FROM skills WHERE id IN ({placeholders})", top_ids
        ).fetchall()
        skill_map = {r["id"]: _row_to_skill(r) for r in rows}

        results: List[SkillMatch] = []
        for sid in top_ids:
            skill = skill_map.get(sid)
            if skill is None:
                continue
            lex = lex_scores.get(sid, 0.0)
            sem = sem_scores.get(sid, 0.0)
            combined = blended[sid]
            if lex > 0 and sem > 0:
                via = "hybrid"
            elif lex > 0:
                via = "lexical"
            else:
                via = "semantic"
            results.append(SkillMatch(
                skill=skill,
                score=combined,
                lexical_score=lex,
                semantic_score=sem,
                matched_via=via,
            ))

        results.sort(key=lambda m: m.score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Stats / lifecycle
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        row = self._read_conn().execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS with_embedding,
                AVG(confidence) AS avg_confidence,
                SUM(use_count) AS total_uses
            FROM skills
            """
        ).fetchone()
        return {
            "total_skills": row["total"] or 0,
            "with_embedding": row["with_embedding"] or 0,
            "avg_confidence": round(row["avg_confidence"] or 0.0, 3),
            "total_uses": row["total_uses"] or 0,
            "db_file": self._db_file,
        }

    def close(self) -> None:
        """Close writer and any thread-local reader connections."""
        with self._lock:
            try:
                self._write_conn.close()
            except Exception:
                pass
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Row → Skill conversion
# ---------------------------------------------------------------------------

def _row_to_skill(row: sqlite3.Row) -> Skill:
    embedding = _blob_to_emb(row["embedding"], row["embedding_dim"])
    return Skill(
        skill_id=row["id"],
        name=row["name"],
        trigger=row["trigger"],
        when_to_use=row["when_to_use"] or "",
        steps=_safe_json(row["steps"], []),
        examples=_safe_json(row["examples"], []),
        support_episode_ids=_safe_json(row["support_episode_ids"], []),
        confidence=float(row["confidence"]),
        embedding=embedding,
        project_id=row["project_id"] or "",
        metadata=_safe_json(row["metadata"], {}),
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        use_count=int(row["use_count"] or 0),
    )


def _safe_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default
