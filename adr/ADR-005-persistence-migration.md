# ADR-005: Persistence & Migration (Minimal)

**Date:** 2026-04-13
**Status:** Accepted
**Deciders:** Jeff Dean

---

## Context

Engram uses four storage backends with different migration characteristics:

| Store | Backend | Migration type |
|-------|---------|----------------|
| Working | SQLite | Schema migration (safe, reversible) |
| Cold | SQLite FTS5 | Schema migration (safe, reversible) |
| Episodic | ChromaDB | Collection migration (semi-reversible) |
| Semantic | Kuzu | Graph schema migration (complex, risky) |
| Neural | File (npz) | Checkpoint migration (model-specific) |

The existing Engram codebase has no schema versioning. This creates a risk:
future changes to the SQLite schema or ChromaDB collection structure will
silently break existing projects if the code is updated without migrating
stored data.

The goal of this ADR is to add **just enough** versioning to protect existing
projects, without building a general-purpose migration framework.

---

## Decision

### Scope: SQLite and ChromaDB only

Kuzu graph migrations and neural checkpoint migrations are **deferred to Phase 2**.
Both are high-risk (Kuzu has no built-in migration tooling; checkpoints are
model-weight-derived and not safely reversible) and neither is likely to change
in the near term.

### 1. Schema version table in each SQLite database

A `_schema_version` table is added to each SQLite database Engram manages:

```sql
CREATE TABLE IF NOT EXISTS _schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT NOT NULL,          -- ISO-8601 timestamp
    description TEXT NOT NULL
);
```

On startup, Engram reads the current version and applies any pending forward
migrations in sequence. If the database is new, all migrations are applied
from version 0.

### 2. ChromaDB collection metadata carries a version field

Each ChromaDB collection created by Engram includes `{"engram_schema_version": N}`
in its metadata. On startup, the episodic store reads this field and applies
collection-level migrations if necessary.

ChromaDB collection migration is limited to:
- Adding metadata fields to existing documents (safe, non-destructive)
- Re-indexing with a new embedding model (requires snapshot first)

Structural changes (changing embedding dimensions) require creating a new
collection and migrating documents in batches. This is a manual operation
documented in the migration guide, not automated.

### 3. Forward-only migration runner

```python
class MigrationRunner:
    def __init__(self, db: sqlite3.Connection, migrations: list[Migration]):
        self.db = db
        self.migrations = {m.version: m for m in migrations}

    def current_version(self) -> int:
        row = self.db.execute(
            "SELECT MAX(version) FROM _schema_version"
        ).fetchone()
        return row[0] or 0

    def migrate(self, target: int | None = None) -> None:
        current = self.current_version()
        target = target or max(self.migrations, default=current)
        if current > target:
            raise RuntimeError(
                f"Cannot roll back from version {current} to {target}. "
                "Restore from snapshot or use a store-specific rollback path."
            )
        for version in range(current + 1, target + 1):
            if version not in self.migrations:
                raise RuntimeError(f"No migration defined for version {version}")
            migration = self.migrations[version]
            migration.up(self.db)
            self.db.execute(
                "INSERT INTO _schema_version (version, applied_at, description) "
                "VALUES (?, datetime('now'), ?)",
                (version, migration.description)
            )
            self.db.commit()
```

Rollback raises explicitly. This is intentional: vector stores, graph stores,
and model-derived artifacts cannot be safely rolled back through schema
reversal. The correct rollback mechanism is a project snapshot (Engram's
existing `snapshot()` / `restore()` API).

### 4. Migration ABC

```python
from abc import ABC, abstractmethod
import sqlite3

class Migration(ABC):
    version: int          # Class attribute, must be unique and sequential
    description: str      # Human-readable description for the version table

    @abstractmethod
    def up(self, db: sqlite3.Connection) -> None:
        """Apply this migration. Must be idempotent."""
        ...
```

Migrations must be **idempotent**: applying the same migration twice must not
corrupt data. Use `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF
NOT EXISTS` (SQLite 3.37+), and similar guards.

### 5. Startup behaviour

Engram's `EngramMemory.__init__()` calls `MigrationRunner.migrate()` before
any other operation. If migration fails, the exception propagates and the
memory system is not available. This is the correct behaviour: operating
against a mismatched schema is worse than failing fast.

### 6. Current schema versions at ADR acceptance

| Store | Current version |
|-------|----------------|
| Working (SQLite) | 1 |
| Cold (SQLite FTS5) | 1 |
| Episodic (ChromaDB) | 1 |

Version 1 represents the schema as it exists in Engram v0.1.19. Any project
created before this ADR is treated as version 0 and will have version 1 applied
on first startup after the update.

---

## Consequences

### Positive

- Existing projects are protected from silent schema breakage on code updates.
- The version table provides an audit trail of when migrations ran.
- Forward-only design eliminates the ambiguity of partial rollbacks.
- Snapshot/restore is the explicit, documented rollback path.

### Negative / Trade-offs

- Startup time increases by one SQLite query per database (negligible).
- Developers adding schema changes must write a `Migration` subclass. This is
  a small, acceptable overhead.
- ChromaDB dimension changes remain a manual operation. Automating this would
  require significant complexity for a rare event.

### Deferred

- **Kuzu graph migration**: Kuzu does not have a migration API comparable to
  SQLite's DDL. Deferred until Kuzu's tooling matures or a workaround is
  designed.
- **Neural checkpoint migration**: Model weight formats are architecture-specific.
  Deferred to Phase 2 when checkpoint versioning is needed.
- **Cross-store transaction**: A migration that touches both SQLite and ChromaDB
  cannot be made atomic. Deferred; for now, each store migrates independently.
  Partial failure leaves a recoverable state (snapshot first, then migrate).

---

## Related

- `contracts/migration.py` (Phase 2): Will formalize `Migration` and
  `MigrationRunner` as contracts. Currently implemented directly in
  `engram/storage/migration.py`.
- ADR-004: Retrieval policy (depends on stable schema for tombstone table)
- Engram snapshot/restore API: The recommended rollback path for failed migrations
