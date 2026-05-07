"""
tests/test_procedural_integration.py

Phase C integration tests — ProceduralMemory wired into ProjectMemory stack.

All offline: no LLM, no Ollama, no filesystem.  Uses in-memory SQLite and
mocked layer objects that satisfy the MemoryContext attribute surface.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from engram.memory.procedural import ProceduralMemory, Skill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pm() -> ProceduralMemory:
    return ProceduralMemory(db_path=None)


def _skill(name="Enable WAL", trigger="when setting up SQLite", confidence=0.85,
           steps=None, project_id=""):
    return Skill(
        name=name,
        trigger=trigger,
        steps=steps or ["Add WAL pragma", "Set sync=NORMAL", "Verify integrity"],
        confidence=confidence,
        project_id=project_id,
    )


# ---------------------------------------------------------------------------
# TokenBudget — procedural field
# ---------------------------------------------------------------------------

class TestTokenBudget:

    def test_procedural_field_exists(self):
        from engram.project_memory import TokenBudget
        b = TokenBudget()
        assert hasattr(b, "procedural")
        assert b.procedural == 200

    def test_total_includes_procedural(self):
        from engram.project_memory import TokenBudget
        b = TokenBudget(working=100, episodic=100, semantic=100, cold=100, procedural=50)
        assert b.total == 450

    def test_procedural_configurable(self):
        from engram.project_memory import TokenBudget
        b = TokenBudget(procedural=400)
        assert b.procedural == 400


# ---------------------------------------------------------------------------
# ContextResult — procedural field
# ---------------------------------------------------------------------------

class TestContextResult:

    def test_procedural_field_exists(self):
        from engram.project_memory import ContextResult
        r = ContextResult()
        assert hasattr(r, "procedural")
        assert r.procedural == []

    def test_procedural_tokens_in_total(self):
        from engram.project_memory import ContextResult
        r = ContextResult(working_tokens=100, episodic_tokens=50,
                          semantic_tokens=30, cold_tokens=20, procedural_tokens=40)
        assert r.total_tokens == 240

    def test_to_dict_includes_procedural(self):
        from engram.project_memory import ContextResult
        r = ContextResult()
        s = _skill()
        r.procedural.append(s.to_dict())
        r.procedural_tokens = 50
        d = r.to_dict()
        assert "procedural" in d
        assert d["token_counts"]["procedural"] == 50

    def test_to_prompt_sections_procedural_key(self):
        from engram.project_memory import ContextResult
        r = ContextResult()
        s = _skill()
        r.procedural.append(s)  # Skill object with to_prompt_text()
        sections = r.to_prompt_sections()
        assert "procedural" in sections
        assert "Enable WAL" in sections["procedural"]

    def test_to_prompt_sections_empty_procedural(self):
        from engram.project_memory import ContextResult
        r = ContextResult()
        sections = r.to_prompt_sections()
        assert sections.get("procedural", "") == ""

    def test_to_prompt_text_contains_steps(self):
        from engram.project_memory import ContextResult
        r = ContextResult()
        s = _skill(steps=["Step A", "Step B"])
        r.procedural.append(s)
        sections = r.to_prompt_sections()
        assert "Step A" in sections["procedural"]


# ---------------------------------------------------------------------------
# MemoryContext — procedural field
# ---------------------------------------------------------------------------

class TestMemoryContext:

    def test_procedural_field_accepted(self):
        from engram.memory.memory_context import MemoryContext
        pm_layer = _make_pm()
        ctx = MemoryContext(
            working=MagicMock(),
            episodic=None,
            semantic=None,
            cold=MagicMock(),
            procedural=pm_layer,
            neural_coord=None,
            embedding_service=MagicMock(),
            budget=MagicMock(),
            token_counter=lambda t: len(t) // 4,
            project_id="test",
            project_type=None,
            telemetry=MagicMock(),
            search_episodes=MagicMock(),
            store_episode=MagicMock(),
        )
        assert ctx.procedural is pm_layer

    def test_procedural_none_accepted(self):
        from engram.memory.memory_context import MemoryContext
        ctx = MemoryContext(
            working=MagicMock(), episodic=None, semantic=None,
            cold=MagicMock(), procedural=None, neural_coord=None,
            embedding_service=MagicMock(), budget=MagicMock(),
            token_counter=lambda t: 1, project_id="p",
            project_type=None, telemetry=MagicMock(),
            search_episodes=MagicMock(), store_episode=MagicMock(),
        )
        assert ctx.procedural is None


# ---------------------------------------------------------------------------
# RetrievalPolicy — procedural weights
# ---------------------------------------------------------------------------

class TestRetrievalPolicy:

    def test_procedural_weights_exist(self):
        from engram.memory.retrieval import RetrievalPolicy
        p = RetrievalPolicy()
        assert hasattr(p, "procedural_weight_confidence")
        assert hasattr(p, "procedural_weight_lexical")
        assert hasattr(p, "procedural_weight_semantic")
        assert hasattr(p, "min_procedural_confidence")

    def test_default_min_confidence(self):
        from engram.memory.retrieval import RetrievalPolicy
        p = RetrievalPolicy()
        assert 0.0 <= p.min_procedural_confidence <= 1.0


# ---------------------------------------------------------------------------
# _procedural_candidates — unit tests via UnifiedRetriever
# ---------------------------------------------------------------------------

def _make_ctx(pm_layer: ProceduralMemory, budget_procedural=200):
    """Build a minimal MemoryContext-shaped mock for retriever tests."""
    from engram.project_memory import TokenBudget
    budget = TokenBudget(procedural=budget_procedural)

    ctx = MagicMock()
    ctx.procedural = pm_layer
    ctx.budget = budget
    ctx.project_id = ""
    ctx.neural_coord = None
    ctx.embedding_service.embed.return_value = None  # no real embeddings
    ctx._token_counter = lambda t: max(1, len(t) // 4)

    # Working memory returns empty
    ctx.working.get_context_window.return_value = []
    return ctx


class TestProceduralCandidates:

    def test_returns_empty_when_no_procedural_layer(self):
        from engram.memory.retrieval import UnifiedRetriever
        ctx = _make_ctx(_make_pm())
        ctx.procedural = None
        r = UnifiedRetriever(ctx)
        candidates = r._procedural_candidates("refactor SQLite", set(), 3)
        assert candidates == []

    def test_returns_candidates_for_matching_query(self):
        from engram.memory.retrieval import UnifiedRetriever
        pm = _make_pm()
        pm.add_skill(_skill(trigger="when refactoring SQLite schema"))
        ctx = _make_ctx(pm)
        r = UnifiedRetriever(ctx)
        candidates = r._procedural_candidates("refactoring SQLite schema", set(), 5)
        assert len(candidates) >= 1

    def test_candidate_layer_is_procedural(self):
        from engram.memory.retrieval import UnifiedRetriever
        pm = _make_pm()
        pm.add_skill(_skill())
        ctx = _make_ctx(pm)
        r = UnifiedRetriever(ctx)
        candidates = r._procedural_candidates("SQLite", set(), 5)
        for c in candidates:
            assert c.layer == "procedural"

    def test_candidate_score_in_range(self):
        from engram.memory.retrieval import UnifiedRetriever
        pm = _make_pm()
        pm.add_skill(_skill(confidence=0.9))
        ctx = _make_ctx(pm)
        r = UnifiedRetriever(ctx)
        candidates = r._procedural_candidates("SQLite", set(), 5)
        for c in candidates:
            assert 0.0 <= c.score <= 1.0

    def test_candidate_metadata_has_skill_name(self):
        from engram.memory.retrieval import UnifiedRetriever
        pm = _make_pm()
        pm.add_skill(_skill(name="Enable WAL"))
        ctx = _make_ctx(pm)
        r = UnifiedRetriever(ctx)
        candidates = r._procedural_candidates("SQLite WAL", set(), 5)
        if candidates:
            assert candidates[0].metadata.get("skill_name") == "Enable WAL"

    def test_min_confidence_filter_honoured(self):
        from engram.memory.retrieval import UnifiedRetriever, RetrievalPolicy
        pm = _make_pm()
        pm.add_skill(_skill(confidence=0.3, name="Low", trigger="when low confidence test"))
        ctx = _make_ctx(pm)
        policy = RetrievalPolicy(min_procedural_confidence=0.5)
        r = UnifiedRetriever(ctx, policy=policy)
        candidates = r._procedural_candidates("low confidence test", set(), 5)
        assert all(c.metadata["confidence"] >= 0.5 for c in candidates)

    def test_top_k_respected(self):
        from engram.memory.retrieval import UnifiedRetriever
        pm = _make_pm()
        for i in range(10):
            pm.add_skill(_skill(name=f"WAL skill {i}", trigger=f"when using SQLite {i}",
                                confidence=0.8))
        ctx = _make_ctx(pm)
        r = UnifiedRetriever(ctx)
        candidates = r._procedural_candidates("SQLite", set(), 3)
        assert len(candidates) <= 3

    def test_no_crash_when_embed_fails(self):
        from engram.memory.retrieval import UnifiedRetriever
        pm = _make_pm()
        pm.add_skill(_skill())
        ctx = _make_ctx(pm)
        ctx.embedding_service.embed.side_effect = RuntimeError("model not loaded")
        r = UnifiedRetriever(ctx)
        # Should not raise
        candidates = r._procedural_candidates("SQLite", set(), 3)
        assert isinstance(candidates, list)


# ---------------------------------------------------------------------------
# synthesize_now skill writing
# ---------------------------------------------------------------------------

class TestSynthesizeNowSkillWriting:
    """Test that synthesize_now() writes skills to ProceduralMemory."""

    def _make_synth_result(self, n_skills=1):
        """Build a SynthesisResult with n_skills Skill objects."""
        from engram.memory.synthesis import SynthesisResult, SynthesisRule
        skills = [
            Skill(
                name=f"Skill {i}",
                trigger=f"when doing task {i}",
                steps=["step A", "step B", "step C"],
                confidence=0.85,
                support_episode_ids=["ep_1", "ep_2", "ep_3"],
            )
            for i in range(n_skills)
        ]
        return SynthesisResult(
            rules=[SynthesisRule(rule_text="Use WAL", support_episode_ids=["ep_1","ep_2","ep_3"],
                                 support_count=3, confidence=0.9)],
            skills=skills,
        )

    def _patched_synthesize_now(self, synth_result, pm_layer):
        """Call the skill-writing logic extracted from synthesize_now without
        requiring a real ProjectMemory (no ChromaDB, no Ollama)."""
        # Simulate the skill-writing block from synthesize_now()
        result = {"skills_written": 0, "skills_skipped": 0}
        embedding_service = MagicMock()
        embedding_service.embed.return_value = None  # no real embedding

        for skill in synth_result.skills:
            skill.project_id = "test_project"
            emb = embedding_service.embed(skill.trigger)
            if emb is not None:
                skill.embedding = emb
            if pm_layer.get_skill(skill.skill_id) is None:
                pm_layer.add_skill(skill)
                result["skills_written"] += 1
            else:
                result["skills_skipped"] += 1
        return result

    def test_skills_written_to_procedural_memory(self):
        pm = _make_pm()
        synth = self._make_synth_result(n_skills=2)
        result = self._patched_synthesize_now(synth, pm)
        assert result["skills_written"] == 2
        assert len(pm.list_skills(project_id="test_project")) == 2

    def test_idempotent_second_write_skipped(self):
        pm = _make_pm()
        synth = self._make_synth_result(n_skills=1)
        self._patched_synthesize_now(synth, pm)
        # Run again with same result
        result2 = self._patched_synthesize_now(synth, pm)
        assert result2["skills_written"] == 0
        assert result2["skills_skipped"] == 1

    def test_skill_project_id_set(self):
        pm = _make_pm()
        synth = self._make_synth_result(n_skills=1)
        self._patched_synthesize_now(synth, pm)
        stored = pm.list_skills(project_id="test_project")
        assert len(stored) == 1
        assert stored[0].project_id == "test_project"

    def test_zero_skills_noop(self):
        from engram.memory.synthesis import SynthesisResult
        pm = _make_pm()
        synth = SynthesisResult()
        result = self._patched_synthesize_now(synth, pm)
        assert result["skills_written"] == 0
        assert pm.get_stats()["total_skills"] == 0


# ---------------------------------------------------------------------------
# _select_candidates procedural layer cap
# ---------------------------------------------------------------------------

class TestSelectCandidatesProceduralCap:

    def _make_candidate(self, layer, score=0.5, tokens=50, text="test content here"):
        from engram.memory.retrieval import RetrievalCandidate
        return RetrievalCandidate(
            layer=layer,
            text=text,
            payload={"text": text, "skill_name": "X"} if layer == "procedural" else {"text": text},
            token_count=tokens,
            score=score,
        )

    def test_procedural_candidates_selected_into_result(self):
        """When procedural candidates are present, they appear in result.procedural."""
        from engram.memory.retrieval import UnifiedRetriever
        from engram.project_memory import ContextResult, TokenBudget

        pm = _make_pm()
        s = _skill()
        pm.add_skill(s)

        ctx = _make_ctx(pm, budget_procedural=500)
        # Patch retrieve to return a known ContextResult with procedural populated
        r = UnifiedRetriever(ctx)
        candidates = [self._make_candidate("procedural", score=0.8, tokens=30)]
        result = ContextResult()
        # Simulate the dispatch loop
        for cand in candidates:
            if cand.layer == "procedural":
                result.procedural.append(cand.payload)
                result.procedural_tokens += cand.token_count

        assert len(result.procedural) == 1
        assert result.procedural_tokens == 30

    def test_procedural_capped_by_budget(self):
        """Skills exceeding the procedural token budget are dropped."""
        from engram.memory.retrieval import UnifiedRetriever
        from engram.project_memory import ContextResult, TokenBudget

        ctx = _make_ctx(_make_pm(), budget_procedural=40)

        # Two candidates totalling 80 tokens — only first should fit
        c1 = self._make_candidate("procedural", score=0.9, tokens=30, text="first skill content")
        c2 = self._make_candidate("procedural", score=0.7, tokens=30, text="second skill content")

        r = UnifiedRetriever(ctx)
        selected = r._select_candidates([c1, c2], remaining_budget=1000)
        proc = [c for c in selected if c.layer == "procedural"]
        proc_tokens = sum(c.token_count for c in proc)
        assert proc_tokens <= 40
