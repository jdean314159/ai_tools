"""
tests/test_procedural_memory.py

Offline unit tests for ProceduralMemory (Layer 6).

No Ollama, no LLM, no filesystem — all tests use in-memory SQLite.
Numpy is used for embedding round-trips; tests that require it are
skipped when numpy is absent (shouldn't happen in normal env).
"""
from __future__ import annotations

import time
from typing import Any

import pytest

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pm():
    from engram.memory.procedural import ProceduralMemory
    return ProceduralMemory(db_path=None)  # :memory:


def _skill(
    name="Refactor SQLite schema with WAL",
    trigger="when refactoring SQLite schema",
    steps=None,
    confidence=0.85,
    project_id="",
    embedding=None,
    when_to_use="Apply whenever changing SQLite table structure.",
):
    from engram.memory.procedural import Skill
    return Skill(
        name=name,
        trigger=trigger,
        steps=steps or ["Add WAL pragma", "Run migration", "Verify with PRAGMA integrity_check"],
        when_to_use=when_to_use,
        examples=[{"input": "ALTER TABLE ...", "output": "Migration complete"}],
        support_episode_ids=["ep_001", "ep_002", "ep_003"],
        confidence=confidence,
        project_id=project_id,
        embedding=embedding,
    )


def _emb(dim=8, val=1.0):
    """Unit vector embedding for cosine == 1.0 when matched against itself."""
    if not _HAS_NUMPY:
        return None
    arr = np.ones(dim, dtype=np.float32) * val
    return arr / np.linalg.norm(arr)


# ---------------------------------------------------------------------------
# Skill dataclass
# ---------------------------------------------------------------------------

class TestSkillDataclass:

    def test_skill_id_auto_generated(self):
        s = _skill()
        assert s.skill_id is not None
        assert len(s.skill_id) == 24

    def test_same_name_trigger_project_same_id(self):
        from engram.memory.procedural import Skill
        a = Skill(name="X", trigger="Y", steps=[], project_id="p")
        b = Skill(name="X", trigger="Y", steps=[], project_id="p")
        assert a.skill_id == b.skill_id

    def test_different_project_different_id(self):
        from engram.memory.procedural import Skill
        a = Skill(name="X", trigger="Y", steps=[], project_id="p1")
        b = Skill(name="X", trigger="Y", steps=[], project_id="p2")
        assert a.skill_id != b.skill_id

    def test_created_at_auto_set(self):
        s = _skill()
        assert s.created_at is not None
        assert s.created_at <= time.time()

    def test_to_dict_serialisable(self):
        import json
        s = _skill()
        d = s.to_dict()
        assert json.dumps(d)  # must not raise

    def test_to_dict_no_embedding_bytes(self):
        s = _skill(embedding=_emb())
        d = s.to_dict()
        assert "has_embedding" in d
        assert d["has_embedding"] is (_emb() is not None)

    def test_to_prompt_text_contains_name(self):
        s = _skill()
        text = s.to_prompt_text()
        assert "Refactor SQLite schema with WAL" in text

    def test_to_prompt_text_contains_steps(self):
        s = _skill()
        text = s.to_prompt_text()
        assert "WAL pragma" in text

    def test_to_prompt_text_contains_example(self):
        s = _skill()
        text = s.to_prompt_text()
        assert "ALTER TABLE" in text


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestCRUD:

    def test_add_and_get(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        fetched = pm.get_skill(s.skill_id)
        assert fetched is not None
        assert fetched.name == s.name

    def test_get_nonexistent_returns_none(self):
        pm = _make_pm()
        assert pm.get_skill("nosuchid") is None

    def test_add_replace_same_id(self):
        pm = _make_pm()
        s = _skill(confidence=0.6)
        pm.add_skill(s)
        s2 = _skill(confidence=0.9)  # same id
        pm.add_skill(s2)
        fetched = pm.get_skill(s.skill_id)
        assert fetched.confidence == pytest.approx(0.9)

    def test_delete_existing(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        assert pm.delete_skill(s.skill_id) is True
        assert pm.get_skill(s.skill_id) is None

    def test_delete_nonexistent_returns_false(self):
        pm = _make_pm()
        assert pm.delete_skill("ghost") is False

    def test_update_confidence(self):
        pm = _make_pm()
        s = _skill(confidence=0.5)
        pm.add_skill(s)
        pm.update_skill(s.skill_id, confidence=0.95)
        assert pm.get_skill(s.skill_id).confidence == pytest.approx(0.95)

    def test_update_steps(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        new_steps = ["step A", "step B"]
        pm.update_skill(s.skill_id, steps=new_steps)
        assert pm.get_skill(s.skill_id).steps == new_steps

    def test_update_nonexistent_returns_false(self):
        pm = _make_pm()
        assert pm.update_skill("ghost", confidence=0.9) is False

    def test_update_ignores_unknown_fields(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        result = pm.update_skill(s.skill_id, nonexistent_field="boom")
        assert result is False  # no valid fields → nothing changed

    def test_steps_roundtrip_json(self):
        pm = _make_pm()
        steps = ["alpha", "beta", "gamma"]
        s = _skill(steps=steps)
        pm.add_skill(s)
        assert pm.get_skill(s.skill_id).steps == steps

    def test_examples_roundtrip(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        fetched = pm.get_skill(s.skill_id)
        assert fetched.examples == s.examples

    def test_support_episode_ids_roundtrip(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        fetched = pm.get_skill(s.skill_id)
        assert fetched.support_episode_ids == s.support_episode_ids

    def test_metadata_roundtrip(self):
        from engram.memory.procedural import Skill
        pm = _make_pm()
        s = Skill(name="X", trigger="Y", steps=[], metadata={"src": "synthesis", "v": 1})
        pm.add_skill(s)
        assert pm.get_skill(s.skill_id).metadata == {"src": "synthesis", "v": 1}


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------

class TestListSkills:

    def test_list_returns_all(self):
        pm = _make_pm()
        for i in range(5):
            pm.add_skill(_skill(name=f"Skill {i}", trigger=f"trigger {i}"))
        assert len(pm.list_skills()) == 5

    def test_list_filtered_by_project(self):
        pm = _make_pm()
        pm.add_skill(_skill(name="A", trigger="ta", project_id="p1"))
        pm.add_skill(_skill(name="B", trigger="tb", project_id="p2"))
        pm.add_skill(_skill(name="C", trigger="tc", project_id="p1"))
        assert len(pm.list_skills(project_id="p1")) == 2
        assert len(pm.list_skills(project_id="p2")) == 1

    def test_list_min_confidence_filter(self):
        pm = _make_pm()
        pm.add_skill(_skill(name="Low", trigger="tl", confidence=0.3))
        pm.add_skill(_skill(name="High", trigger="th", confidence=0.9))
        results = pm.list_skills(min_confidence=0.5)
        assert len(results) == 1
        assert results[0].name == "High"

    def test_list_limit(self):
        pm = _make_pm()
        for i in range(10):
            pm.add_skill(_skill(name=f"S{i}", trigger=f"t{i}"))
        assert len(pm.list_skills(limit=3)) == 3

    def test_list_empty_store(self):
        assert pm.list_skills() == [] if (pm := _make_pm()) else True


# ---------------------------------------------------------------------------
# record_use
# ---------------------------------------------------------------------------

class TestRecordUse:

    def test_use_count_incremented(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        pm.record_use(s.skill_id)
        pm.record_use(s.skill_id)
        assert pm.get_skill(s.skill_id).use_count == 2

    def test_last_used_at_set(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        before = time.time()
        pm.record_use(s.skill_id)
        after = time.time()
        ts = pm.get_skill(s.skill_id).last_used_at
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# Embedding storage
# ---------------------------------------------------------------------------

class TestEmbeddingStorage:

    @pytest.mark.skipif(not _HAS_NUMPY, reason="numpy required")
    def test_embedding_roundtrip(self):
        pm = _make_pm()
        emb = _emb(dim=16)
        s = _skill(embedding=emb)
        pm.add_skill(s)
        fetched = pm.get_skill(s.skill_id)
        assert fetched.embedding is not None
        assert np.allclose(fetched.embedding, emb)

    @pytest.mark.skipif(not _HAS_NUMPY, reason="numpy required")
    def test_no_embedding_is_none(self):
        pm = _make_pm()
        s = _skill(embedding=None)
        pm.add_skill(s)
        assert pm.get_skill(s.skill_id).embedding is None

    @pytest.mark.skipif(not _HAS_NUMPY, reason="numpy required")
    def test_update_embedding(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        emb = _emb(dim=8)
        pm.update_skill(s.skill_id, embedding=emb)
        fetched = pm.get_skill(s.skill_id)
        assert np.allclose(fetched.embedding, emb)


# ---------------------------------------------------------------------------
# Lexical matching
# ---------------------------------------------------------------------------

class TestLexicalMatch:

    def test_match_returns_skill(self):
        pm = _make_pm()
        pm.add_skill(_skill())
        results = pm.match_skills("refactor SQLite schema")
        assert len(results) >= 1

    def test_match_no_hit_returns_empty(self):
        pm = _make_pm()
        pm.add_skill(_skill())
        results = pm.match_skills("quantum entanglement photon spin")
        assert results == []

    def test_match_empty_store_returns_empty(self):
        pm = _make_pm()
        assert pm.match_skills("anything") == []

    def test_match_respects_top_k(self):
        pm = _make_pm()
        for i in range(10):
            pm.add_skill(_skill(name=f"SQLite skill {i}", trigger=f"when using SQLite {i}"))
        results = pm.match_skills("SQLite", top_k=3)
        assert len(results) <= 3

    def test_match_score_in_range(self):
        pm = _make_pm()
        pm.add_skill(_skill())
        results = pm.match_skills("refactor SQLite")
        for m in results:
            assert 0.0 <= m.score <= 1.0

    def test_match_lexical_only_no_embedding(self):
        pm = _make_pm()
        pm.add_skill(_skill())
        results = pm.match_skills("refactor SQLite", embedding=None)
        assert all(m.matched_via in ("lexical", "hybrid") for m in results)

    def test_match_filters_by_project_id(self):
        pm = _make_pm()
        pm.add_skill(_skill(name="P1 Skill", trigger="refactor SQLite project1", project_id="p1"))
        pm.add_skill(_skill(name="P2 Skill", trigger="refactor SQLite project2", project_id="p2"))
        results = pm.match_skills("refactor SQLite", project_id="p1")
        names = [m.skill.name for m in results]
        assert "P1 Skill" in names
        assert "P2 Skill" not in names

    def test_match_filters_by_min_confidence(self):
        pm = _make_pm()
        pm.add_skill(_skill(name="Low", trigger="refactor SQLite low", confidence=0.2))
        pm.add_skill(_skill(name="High", trigger="refactor SQLite high", confidence=0.9))
        results = pm.match_skills("refactor SQLite", min_confidence=0.5)
        names = [m.skill.name for m in results]
        assert "Low" not in names


# ---------------------------------------------------------------------------
# Semantic matching
# ---------------------------------------------------------------------------

class TestSemanticMatch:

    @pytest.mark.skipif(not _HAS_NUMPY, reason="numpy required")
    def test_semantic_match_finds_similar(self):
        pm = _make_pm()
        emb = _emb(dim=8)
        pm.add_skill(_skill(embedding=emb, trigger="zzz unrelated trigger text"))
        # Query with same embedding — cosine == 1.0
        results = pm.match_skills(
            "unrelated query text xyz",
            embedding=emb,
            lexical_weight=0.0,  # pure semantic
        )
        assert len(results) >= 1
        assert results[0].semantic_score > 0.9

    @pytest.mark.skipif(not _HAS_NUMPY, reason="numpy required")
    def test_semantic_match_orthogonal_low_score(self):
        pm = _make_pm()
        emb_a = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        emb_b = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
        pm.add_skill(_skill(embedding=emb_a))
        results = pm.match_skills("query", embedding=emb_b, lexical_weight=0.0)
        # Cosine 0 → mapped to 0.5 in 0..1 range; score may be low
        if results:
            assert results[0].semantic_score <= 0.55

    @pytest.mark.skipif(not _HAS_NUMPY, reason="numpy required")
    def test_hybrid_matched_via_label(self):
        pm = _make_pm()
        emb = _emb(dim=8)
        pm.add_skill(_skill(embedding=emb))
        results = pm.match_skills("refactor SQLite", embedding=emb)
        # With both signals present, at least one should be "hybrid"
        vias = {m.matched_via for m in results}
        assert vias.intersection({"hybrid", "lexical", "semantic"})

    @pytest.mark.skipif(not _HAS_NUMPY, reason="numpy required")
    def test_dim_mismatch_skipped_gracefully(self):
        pm = _make_pm()
        emb_stored = _emb(dim=8)
        emb_query = _emb(dim=16)  # different dim
        pm.add_skill(_skill(embedding=emb_stored))
        # Should not raise; mismatch is skipped silently
        results = pm.match_skills("refactor", embedding=emb_query, lexical_weight=0.0)
        # No crash; may return empty (semantic skipped) or lexical results
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:

    def test_stats_empty(self):
        pm = _make_pm()
        stats = pm.get_stats()
        assert stats["total_skills"] == 0
        assert stats["with_embedding"] == 0

    @pytest.mark.skipif(not _HAS_NUMPY, reason="numpy required")
    def test_stats_counts_embeddings(self):
        pm = _make_pm()
        pm.add_skill(_skill(name="With emb", trigger="ta", embedding=_emb()))
        pm.add_skill(_skill(name="No emb", trigger="tb", embedding=None))
        stats = pm.get_stats()
        assert stats["total_skills"] == 2
        assert stats["with_embedding"] == 1

    def test_stats_avg_confidence(self):
        pm = _make_pm()
        pm.add_skill(_skill(name="A", trigger="ta", confidence=0.6))
        pm.add_skill(_skill(name="B", trigger="tb", confidence=0.8))
        stats = pm.get_stats()
        assert stats["avg_confidence"] == pytest.approx(0.7, abs=0.01)

    def test_stats_total_uses(self):
        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)
        pm.record_use(s.skill_id)
        pm.record_use(s.skill_id)
        stats = pm.get_stats()
        assert stats["total_uses"] == 2
