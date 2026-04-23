from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path


def _engine():
    class Eng:
        model_name = "test-model"
        system_prompt = "You are a helpful assistant."
        is_cloud = False
        max_context_length = 4096

        def count_tokens(self, t):
            return max(1, len(t) // 4)

        def compress_prompt(self, p, target_tokens):
            return p[: target_tokens * 4]

    return Eng()


def _make_pm(tmpdir):
    from engram.project_memory import ProjectMemory, TokenBudget

    budget = TokenBudget(working=400, episodic=400, semantic=300, cold=300)
    return ProjectMemory(
        project_id="prompt_canonicalization_test",
        project_type="general",
        base_dir=Path(tmpdir),
        llm_engine=_engine(),
        token_budget=budget,
    )


def _build_cold_prompt(pm, question: str, query: str) -> str:
    from engram.project_memory import ProjectMemory, TokenBudget

    pm._event_bus._queue.join()
    base_dir = Path(pm._project_dir).parent
    project_id = pm.project_id
    project_type = pm.project_type
    pm.close()
    cold = ProjectMemory(
        project_id=project_id,
        project_type=project_type,
        base_dir=base_dir,
        session_id="cold",
        llm_engine=_engine(),
        token_budget=TokenBudget(working=400, episodic=400, semantic=300, cold=300),
    )
    try:
        built = cold.build_prompt(question, query=query)
        return built["prompt"].lower()
    finally:
        cold.close()


def test_docs_prompt_uses_canonical_text_without_old_location():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Preference: keep durable project docs in Markdown files committed to the repo, not in Google Docs.")
            prompt = _build_cold_prompt(pm, "Where should durable project documentation live?", "Where should durable project documentation live?")
            assert "markdown" in prompt
            assert "repo" in prompt
            assert "google docs" not in prompt
            assert "surface_text" not in prompt
            assert "old_value" not in prompt
            assert "match_score" not in prompt


def test_schedule_prompt_uses_updated_value_without_stale_day():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Update: the weekly architecture review has moved to Wednesday at 2 PM, not Tuesday.")
            prompt = _build_cold_prompt(pm, "When is the architecture review now scheduled?", "When is the architecture review now scheduled?")
            assert "wednesday" in prompt
            assert "2 pm" in prompt
            assert "tuesday" not in prompt


def test_model_update_prompt_uses_current_model_without_superseded_model():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Correction: for long batch summaries, prefer qwen3:32b instead of qwen3:8b.")
            prompt = _build_cold_prompt(pm, "Which model should handle long batch summaries?", "Which model should handle long batch summaries?")
            assert "qwen3:32b" in prompt
            assert "qwen3:8b" not in prompt


def test_transient_note_is_not_stored_as_durable_memory():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Transient note: I am only asking about Tuesday because I was mistaken.")
            pm._event_bus._queue.join()
            facts = pm.semantic.list_facts(limit=20)
            contents = [row["content"].lower() for row in facts]
            assert not any("mistaken" in content for content in contents)
            assert not any("tuesday" in content for content in contents)
            episodes = pm.search_episodes("tuesday mistaken", n=10)
            assert not any("mistaken" in getattr(ep, "text", "").lower() for ep in episodes)


def test_contextresult_canonicalizes_episodic_updates_for_prompt_sections():
    from engram.project_memory import ContextResult

    @dataclass
    class EpisodeLike:
        text: str

    ctx = ContextResult(
        episodic=[
            EpisodeLike("Preference: keep durable project docs in Markdown files committed to the repo, not in Google Docs."),
            EpisodeLike("Update: the weekly architecture review has moved to Wednesday at 2 PM, not Tuesday."),
            EpisodeLike("Correction: for long batch summaries, prefer qwen3:32b instead of qwen3:8b."),
            EpisodeLike("Transient note: I am only asking about Tuesday because I was mistaken."),
        ]
    )
    episodic = ctx.to_prompt_sections()["episodic"].lower()
    assert "google docs" not in episodic
    assert "tuesday" not in episodic
    assert "qwen3:8b" not in episodic
    assert "markdown" in episodic
    assert "wednesday" in episodic
    assert "qwen3:32b" in episodic
    assert "mistaken" not in episodic
