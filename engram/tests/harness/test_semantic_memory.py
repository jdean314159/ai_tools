"""Tests for SemanticMemory (Layer 3) — Kuzu graph database."""

from __future__ import annotations

import time

from .runner import test_group, require
from .mocks import TempDir


def _make_semantic(db_path, project_type=None):
    require("kuzu")
    from engram.memory.semantic_memory import SemanticMemory
    from engram.memory.types import ProjectType
    pt = project_type or ProjectType.PROGRAMMING_ASSISTANT
    return SemanticMemory(db_path=db_path, project_type=pt)


# ── Schema / init ─────────────────────────────────────────────────────────────

@test_group("Semantic Memory")
def test_semantic_add_preference():
    with TempDir() as d:
        sm = _make_semantic(d / "sem")
        sm.add_preference(category="testing", value="pytest over unittest", strength=0.85)
        rows = sm.list_preferences(limit=10)
        assert len(rows) >= 1
        assert any("pytest" in r.get("value", "") for r in rows)

@test_group("Semantic Memory")
def test_semantic_persistence():
    """Graph data survives close/reopen."""
    from engram.memory.semantic_memory import SemanticMemory
    from engram.memory.types import ProjectType

    with TempDir() as d:
        db_path = d / "sem"
        sm1 = SemanticMemory(db_path=db_path)
        sm1.add_fact("Persistent fact for testing", confidence=0.8)
        sm1.close()
        sm2 = SemanticMemory(db_path=db_path)
        rows = sm2.list_facts(limit=10)
        assert len(rows) >= 1


# ── search_generic_memories (previously SemanticSearchMixin, now inline in SemanticMemory) ──

@test_group("Semantic Memory")
def test_helpers_language_tutor_add_and_retrieve():
    """add_vocabulary + find_unmastered_words round-trip."""
    with TempDir() as d:
        sm = _make_sem_sqlite(d / "sem_tutor")
        from engram.memory.semantic_helpers import LanguageTutorHelpers
        h = LanguageTutorHelpers(sm)

        h.add_vocabulary("w1", "hola", "hello", language="spanish", difficulty="beginner")
        h.add_vocabulary("w2", "gracias", "thank you", language="spanish", difficulty="beginner")
        h.add_vocabulary("w3", "subjuntivo", "subjunctive", language="spanish", difficulty="advanced")

        unmastered = h.find_unmastered_words("user_jeff", difficulty="beginner", language="spanish")
        words = {r["word"] for r in unmastered}
        assert "hola" in words
        assert "gracias" in words
        assert "subjuntivo" not in words  # wrong difficulty


@test_group("Semantic Memory")
def test_helpers_mastery_filters_unmastered():
    """track_mastery removes a word from find_unmastered_words."""
    with TempDir() as d:
        sm = _make_sem_sqlite(d / "sem_mastery")
        from engram.memory.semantic_helpers import LanguageTutorHelpers
        h = LanguageTutorHelpers(sm)

        h.add_vocabulary("w1", "hola", "hello", language="spanish", difficulty="beginner")
        h.add_vocabulary("w2", "gracias", "thank you", language="spanish", difficulty="beginner")

        # Master only "hola"
        h.track_mastery("user_jeff", "w1", mastery_level=0.95, language="spanish")

        unmastered = h.find_unmastered_words("user_jeff", difficulty="beginner", language="spanish")
        words = {r["word"] for r in unmastered}
        assert "hola" not in words
        assert "gracias" in words


@test_group("Semantic Memory")
def test_helpers_find_mastered_words():
    """find_mastered_words returns only words at or above threshold."""
    with TempDir() as d:
        sm = _make_sem_sqlite(d / "sem_mastered")
        from engram.memory.semantic_helpers import LanguageTutorHelpers
        h = LanguageTutorHelpers(sm)

        h.add_vocabulary("w1", "hola", "hello", language="spanish", difficulty="beginner")
        h.add_vocabulary("w2", "adios", "goodbye", language="spanish", difficulty="beginner")

        h.track_mastery("user_jeff", "w1", 0.9, language="spanish")
        h.track_mastery("user_jeff", "w2", 0.5, language="spanish")  # below threshold

        mastered = h.find_mastered_words("user_jeff", language="spanish", min_strength=0.8)
        ids = {r["word_id"] for r in mastered}
        assert "w1" in ids
        assert "w2" not in ids


@test_group("Semantic Memory")
def test_helpers_programming_store_and_find_bug():
    """store_bug + find_similar_bugs via FTS."""
    with TempDir() as d:
        from engram.memory.semantic_memory import SemanticMemory
        from engram.memory.types import ProjectType
        sm = SemanticMemory(db_path=d / "sem_prog", project_type=ProjectType.PROGRAMMING_ASSISTANT)
        from engram.memory.semantic_helpers import ProgrammingAssistantHelpers
        h = ProgrammingAssistantHelpers(sm)

        h.store_bug(
            "ImportError",
            "No module named 'chromadb'",
            "pip install chromadb",
        )
        h.store_bug(
            "RuntimeError",
            "CUDA out of memory",
            "Reduce batch size or use --num-gpu 0",
        )

        results = h.find_similar_bugs("chromadb import error")
        assert len(results) >= 1
        texts = " ".join(r.get("content", "") for r in results)
        assert "chromadb" in texts.lower()


@test_group("Semantic Memory")
def test_helpers_graph_methods_return_empty_with_warning(caplog_or_none=None):
    """Graph-only methods return [] without raising."""
    with TempDir() as d:
        sm = _make_sem_sqlite(d / "sem_graph")
        from engram.memory.semantic_helpers import (
            LanguageTutorHelpers,
            ProgrammingAssistantHelpers,
        )
        lt = LanguageTutorHelpers(sm)
        pa = ProgrammingAssistantHelpers(sm)

        assert lt.find_learning_path_for_concept("subjunctive") == []
        assert pa.find_learning_path("recursion") == []
        assert pa.find_prerequisites("async") == []
        assert pa.find_alternatives("snippet_42") == []
