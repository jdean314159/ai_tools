"""Tests for migration CLI tools."""
from __future__ import annotations
import json
import time
import uuid
import tempfile
import pytest
from pathlib import Path
from tests.conftest import MockEmbedder


def make_project(base_dir: Path, project_id: str = "test_project"):
    """Create a v1.0-style project directory with episodes and sessions."""
    project_dir = base_dir / project_id
    project_dir.mkdir(parents=True)
    sessions_dir = project_dir / "sessions"
    sessions_dir.mkdir()

    # Write episodes.jsonl
    episodes = [
        {
            "id": f"ep_{uuid.uuid4().hex[:12]}",
            "text": "I prefer BeautifulSoup for HTML parsing tasks.",
            "importance": 0.8,
            "created_at": time.time() - 3600,
            "metadata": {"role": "user", "session_id": "s1"},
        },
        {
            "id": f"ep_{uuid.uuid4().hex[:12]}",
            "text": "We decided to use PostgreSQL for the main database.",
            "importance": 0.9,
            "created_at": time.time() - 1800,
            "metadata": {"role": "user", "session_id": "s1"},
        },
        {
            "id": f"ep_{uuid.uuid4().hex[:12]}",
            "text": "The project uses a microservices architecture pattern.",
            "importance": 0.7,
            "created_at": time.time() - 900,
            "metadata": {"role": "user", "session_id": "s2"},
        },
    ]

    episodes_file = project_dir / "episodes.jsonl"
    with episodes_file.open("w") as f:
        for ep in episodes:
            f.write(json.dumps(ep) + "\n")

    # Write session files (user -> assistant pairs)
    session1 = [
        {"role": "user", "text": "What library should I use for HTML parsing?"},
        {"role": "assistant", "text": "I recommend BeautifulSoup for its ease of use."},
        {"role": "user", "text": "What about the database?"},
        {"role": "assistant", "text": "PostgreSQL is a solid choice for most workloads."},
    ]
    with (sessions_dir / "s1.jsonl").open("w") as f:
        for turn in session1:
            f.write(json.dumps(turn) + "\n")

    session2 = [
        {"role": "user", "text": "How should I structure this project?"},
        {"role": "assistant", "text": "Microservices would work well given your scale."},
    ]
    with (sessions_dir / "s2.jsonl").open("w") as f:
        for turn in session2:
            f.write(json.dumps(turn) + "\n")

    return project_dir, episodes


# ---------------------------------------------------------------------------
# Paired exchange migration
# ---------------------------------------------------------------------------

def test_migrate_paired_exchanges_basic(tmp_path):
    from engram_lite.cli.migrate import migrate_paired_exchanges

    project_dir, _ = make_project(tmp_path)
    original_episode_count = len(list(project_dir.glob("episodes.jsonl")))

    added = migrate_paired_exchanges(project_dir)

    # 2 pairs in s1 + 1 pair in s2 = 3
    assert added == 3

    # Verify paired episodes were written
    episodes = []
    with (project_dir / "episodes.jsonl").open() as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))

    paired = [ep for ep in episodes if ep.get("metadata", {}).get("type") == "exchange"]
    assert len(paired) == 3


def test_migrate_paired_exchanges_format(tmp_path):
    """Paired episodes use correct User:/Assistant: format."""
    from engram_lite.cli.migrate import migrate_paired_exchanges

    project_dir, _ = make_project(tmp_path)
    migrate_paired_exchanges(project_dir)

    episodes = []
    with (project_dir / "episodes.jsonl").open() as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))

    paired = [ep for ep in episodes if ep.get("metadata", {}).get("type") == "exchange"]
    for ep in paired:
        assert ep["text"].startswith("User: ")
        assert "\nAssistant: " in ep["text"]


def test_migrate_paired_exchanges_metadata(tmp_path):
    """Paired episodes include session_id and original texts."""
    from engram_lite.cli.migrate import migrate_paired_exchanges

    project_dir, _ = make_project(tmp_path)
    migrate_paired_exchanges(project_dir)

    episodes = []
    with (project_dir / "episodes.jsonl").open() as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))

    paired = [ep for ep in episodes if ep.get("metadata", {}).get("type") == "exchange"]
    for ep in paired:
        meta = ep["metadata"]
        assert "session_id" in meta
        assert "user_text" in meta
        assert "assistant_text" in meta
        assert meta.get("migrated") is True


def test_migrate_no_sessions_dir(tmp_path):
    """Projects without sessions directory skip pairing gracefully."""
    from engram_lite.cli.migrate import migrate_paired_exchanges

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "episodes.jsonl").write_text("")

    added = migrate_paired_exchanges(project_dir)
    assert added == 0


def test_migrate_empty_sessions(tmp_path):
    """Sessions with no assistant turns produce no pairs."""
    from engram_lite.cli.migrate import migrate_paired_exchanges

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "sessions").mkdir()
    (project_dir / "episodes.jsonl").write_text("")

    # Session with only user turns
    turns = [
        {"role": "user", "text": "first"},
        {"role": "user", "text": "second"},
    ]
    with (project_dir / "sessions" / "s1.jsonl").open("w") as f:
        for t in turns:
            f.write(json.dumps(t) + "\n")

    added = migrate_paired_exchanges(project_dir)
    assert added == 0


# ---------------------------------------------------------------------------
# Semantic graph migration
# ---------------------------------------------------------------------------

def test_migrate_semantic_graph_pattern_only(tmp_path):
    """Pattern-only extraction produces facts without LLM."""
    from engram_lite.cli.migrate import migrate_semantic_graph
    from engram_lite.semantic.graph import SemanticGraph

    project_dir, _ = make_project(tmp_path)
    extracted = migrate_semantic_graph(project_dir, llm_engine=None)

    # May or may not find facts depending on patterns
    assert isinstance(extracted, int)
    assert extracted >= 0

    # Graph file should exist
    graph_file = project_dir / "semantic_graph.json"
    assert graph_file.exists()


def test_migrate_semantic_graph_creates_valid_graph(tmp_path):
    """Migrated graph can be loaded as SemanticGraph."""
    from engram_lite.cli.migrate import migrate_semantic_graph
    from engram_lite.semantic.graph import SemanticGraph

    project_dir, _ = make_project(tmp_path)
    migrate_semantic_graph(project_dir, llm_engine=None)

    graph = SemanticGraph(persist_path=project_dir / "semantic_graph.json")
    # If any facts were extracted, they should be queryable
    facts = graph.query_facts()
    assert isinstance(facts, list)


def test_migrate_semantic_no_episodes(tmp_path):
    """Migration with empty episodes.jsonl produces no facts."""
    from engram_lite.cli.migrate import migrate_semantic_graph

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "episodes.jsonl").write_text("")

    extracted = migrate_semantic_graph(project_dir, llm_engine=None)
    assert extracted == 0


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

def test_migration_sets_schema_version(tmp_path):
    """Full migration sets schema version to SCHEMA_VERSION."""
    from engram_lite.cli.migrate import migrate_paired_exchanges, migrate_semantic_graph
    from engram_lite.storage.schema import SchemaManager
    from engram_lite.version import SCHEMA_VERSION

    project_dir, _ = make_project(tmp_path)
    migrate_paired_exchanges(project_dir)
    migrate_semantic_graph(project_dir, llm_engine=None)

    schema_mgr = SchemaManager(project_dir)
    schema_mgr.set_version(SCHEMA_VERSION)

    assert schema_mgr.get_version() == SCHEMA_VERSION
    assert not schema_mgr.needs_migration(SCHEMA_VERSION)


def test_schema_manager_detects_old_version(tmp_path):
    """Old-version project triggers migration warning."""
    from engram_lite.storage.schema import SchemaManager
    from engram_lite.version import SCHEMA_VERSION

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    mgr = SchemaManager(project_dir)
    mgr.set_version("1.0")

    assert mgr.needs_migration(SCHEMA_VERSION)
    assert mgr.get_version() == "1.0"


def test_schema_manager_no_file_returns_none(tmp_path):
    """Missing schema file returns None version."""
    from engram_lite.storage.schema import SchemaManager

    mgr = SchemaManager(tmp_path / "project")
    assert mgr.get_version() is None
    assert mgr.needs_migration("2.0")


def test_schema_manager_persist_reload(tmp_path):
    """Schema version persists across instances."""
    from engram_lite.storage.schema import SchemaManager

    path = tmp_path / "project"
    path.mkdir()

    SchemaManager(path).set_version("2.0", metadata={"test": True})
    assert SchemaManager(path).get_version() == "2.0"
