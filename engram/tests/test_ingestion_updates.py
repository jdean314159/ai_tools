from __future__ import annotations

import tempfile
from pathlib import Path


def _engine():
    class Eng:
        model_name = "test-model"
        system_prompt = "You are a helpful assistant."
        is_cloud = False
        max_context_length = 2048
        def count_tokens(self, t): return max(1, len(t) // 4)
        def compress_prompt(self, p, target_tokens): return p[:target_tokens * 4]
    return Eng()


def _make_pm(tmpdir):
    from engram.project_memory import ProjectMemory, TokenBudget
    budget = TokenBudget(working=400, episodic=400, semantic=300, cold=300)
    return ProjectMemory(
        project_id="ingestion_update_test",
        project_type="general",
        base_dir=Path(tmpdir),
        llm_engine=_engine(),
        token_budget=budget,
    )


def test_correction_fact_is_canonicalized_for_semantic_memory():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Correction: for analytics, use DuckDB locally instead of SQLite.")
            pm._event_bus._queue.join()
            rows = pm.semantic.list_facts(limit=20)
            contents = [row["content"].lower() for row in rows]
            assert any("duckdb" in content and "analytics" in content for content in contents)
            assert not any("instead of sqlite" in content for content in contents)


def test_schedule_update_fact_drops_stale_value_from_canonical_fact():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Update: the weekly architecture review has moved to Wednesday at 2 PM, not Tuesday.")
            pm._event_bus._queue.join()
            rows = pm.semantic.list_facts(limit=20)
            contents = [row["content"].lower() for row in rows]
            assert any("weekly architecture review" in content and "wednesday" in content for content in contents)
            assert not any("tuesday" in content for content in contents)


def test_region_update_fact_drops_obsolete_region_from_canonical_fact():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Update: deploy the nightly evaluation job in us-west-2, not us-east-1.")
            pm._event_bus._queue.join()
            rows = pm.semantic.list_facts(limit=20)
            contents = [row["content"].lower() for row in rows]
            assert any("nightly evaluation job" in content and "us-west-2" in content for content in contents)
            assert not any("us-east-1" in content for content in contents)



def test_prefer_update_fact_drops_obsolete_model_from_canonical_fact():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Correction: for long batch summaries, prefer qwen3:32b instead of qwen3:8b.")
            pm._event_bus._queue.join()
            rows = pm.semantic.list_facts(limit=20)
            contents = [row["content"].lower() for row in rows]
            assert any("long batch summaries" in content and "qwen3:32b" in content for content in contents)
            assert not any("qwen3:8b" in content for content in contents)



def test_preference_location_fact_is_canonicalized_without_obsolete_alternative():
    with tempfile.TemporaryDirectory() as td:
        with _make_pm(td) as pm:
            pm.add_turn("user", "Preference: keep durable project docs in Markdown files committed to the repo, not in Google Docs.")
            pm._event_bus._queue.join()
            rows = pm.semantic.list_facts(limit=20)
            contents = [row["content"].lower() for row in rows]
            assert any("durable project docs" in content and "markdown" in content and "repo" in content for content in contents)
            assert not any("google docs" in content for content in contents)
