from __future__ import annotations

from engram import ProjectMemory


def test_store_episode_filters_ephemeral_noise() -> None:
    memory = ProjectMemory(session_id="s1")

    episode_id = memory.store_episode(
        "Temporary note: ignore this for this message only.",
        importance=0.6,
    )

    assert episode_id == ""
    assert memory.get_stats()["episodic"]["count"] == 0
    assert memory.get_stats()["episodic"]["quality"]["filtered"] >= 1


def test_store_episode_blocks_near_duplicates() -> None:
    memory = ProjectMemory(session_id="s1")

    first = memory.store_episode(
        "We decided to use SQLite for the lightweight semantic store.",
        importance=0.9,
        bypass_filter=True,
    )
    second = memory.store_episode(
        "We decided to use SQLite for the lightweight semantic store",
        importance=0.85,
        bypass_filter=True,
    )

    assert first
    assert second == ""
    assert memory.get_stats()["episodic"]["count"] == 1
    assert memory.get_stats()["episodic"]["quality"]["dedup_blocked"] >= 1


def test_search_episodes_scores_and_deduplicates_results() -> None:
    memory = ProjectMemory(session_id="s1")
    memory.store_episode(
        "The project decision was to use SQLite for semantic memory and JSONL for session logs.",
        importance=0.95,
        bypass_filter=True,
    )
    memory.store_episode(
        "Project decision: use SQLite for semantic memory and JSONL for session logs.",
        importance=0.92,
        bypass_filter=True,
    )
    memory.store_episode(
        "The team plans to compare qwen models in the inspector UI next week.",
        importance=0.65,
        bypass_filter=True,
    )

    results = memory.search_episodes("sqlite semantic memory", n=5)

    assert results
    assert "SQLite" in results[0].text
    assert len(results) == 1 or all(
        "SQLite" not in item.text or item is results[0] for item in results[1:]
    )


def test_build_prompt_uses_internal_episode_retrieval_without_external_retriever() -> None:
    memory = ProjectMemory(session_id="s1")
    memory.store_episode(
        "The user prefers concise architectural summaries and wants VISION.md treated as canonical.",
        importance=0.95,
        bypass_filter=True,
    )

    result = memory.build_prompt("What should I use as the canonical architecture document?")

    assert "VISION.md treated as canonical" in result["prompt"]
    assert result["memory_tokens"] > 0


def test_add_turn_can_auto_ingest_high_value_turns() -> None:
    memory = ProjectMemory(session_id="s1")

    memory.add_turn(
        "user",
        "Important: remember that I prefer concise architectural summaries and use VISION.md as the source of truth.",
        session_id="s1",
    )

    results = memory.search_episodes("source of truth", n=5)
    stats = memory.get_stats()

    assert results
    assert "VISION.md" in results[0].text
    assert stats["episodic"]["quality"]["auto_ingested"] >= 1


def test_add_turn_does_not_auto_ingest_assistant_turns_by_default() -> None:
    memory = ProjectMemory(session_id="s1")

    memory.add_turn(
        "assistant",
        "Important: remember that VISION.md is the source of truth for this repo.",
        session_id="s1",
    )

    results = memory.search_episodes("source of truth", n=5)
    stats = memory.get_stats()

    assert results == []
    assert stats["episodic"]["quality"]["assistant_auto_ingest_skipped"] >= 1


def test_store_episode_allows_explicit_assistant_summary_types() -> None:
    memory = ProjectMemory(session_id="s1")

    episode_id = memory.store_episode(
        "Session summary: the user wants concise architectural summaries and VISION.md as canonical.",
        metadata={"role": "assistant", "kind": "session_summary"},
        importance=0.95,
    )

    results = memory.search_episodes("canonical", n=5)

    assert episode_id
    assert results
    assert "VISION.md" in results[0].text


def test_store_episode_filters_generic_assistant_outputs_without_explicit_type() -> None:
    memory = ProjectMemory(session_id="s1")

    episode_id = memory.store_episode(
        "You should probably refactor the module and maybe add more comments.",
        metadata={"role": "assistant"},
        importance=0.95,
    )

    assert episode_id == ""


def test_add_turn_auto_ingests_canonical_correction_updates() -> None:
    memory = ProjectMemory(session_id="s1")

    memory.add_turn(
        "user",
        "Correction: for analytics, use DuckDB locally instead of SQLite.",
        session_id="s1",
    )

    results = memory.search_episodes("local database for analytics", n=5)

    assert results
    assert "DuckDB" in results[0].text
    assert "SQLite for analytics" not in results[0].text


def test_add_turn_auto_ingests_schedule_updates() -> None:
    memory = ProjectMemory(session_id="s1")

    memory.add_turn(
        "user",
        "Update: the weekly architecture review has moved to Wednesday at 2 PM, not Tuesday.",
        session_id="s1",
    )

    results = memory.search_episodes("weekly architecture review time", n=5)

    assert results
    assert "Wednesday at 2 PM" in results[0].text
    assert "Tuesday" not in results[0].text


def test_store_episode_replaces_prior_topic_updates() -> None:
    memory = ProjectMemory(session_id="s1")

    first = memory.store_episode(
        "Update: the weekly architecture review has moved to Tuesday at 1 PM, not Monday.",
        importance=0.9,
    )
    second = memory.store_episode(
        "Update: the weekly architecture review has moved to Wednesday at 2 PM, not Tuesday.",
        importance=0.95,
    )

    results = memory.search_episodes("weekly architecture review time", n=5)
    stats = memory.get_stats()

    assert first
    assert second
    assert len(results) == 1
    assert "Wednesday at 2 PM" in results[0].text
    assert stats["episodic"]["count"] == 1
    assert stats["episodic"]["quality"]["topic_replaced"] >= 1


def test_store_episode_canonicalizes_docs_location_preference() -> None:
    memory = ProjectMemory(session_id="s1")

    episode_id = memory.store_episode(
        "Preference: keep durable project docs in Markdown files committed to the repo, not in Google Docs.",
        importance=0.9,
    )

    results = memory.search_episodes("Where should durable project documentation live?", n=5)

    assert episode_id
    assert results
    assert "Markdown" in results[0].text
    assert "repo" in results[0].text.lower()
    assert "Google Docs" not in results[0].text


def test_add_turn_auto_ingests_region_and_model_updates() -> None:
    memory = ProjectMemory(session_id="s1")

    memory.add_turn(
        "user",
        "Update: deploy the nightly evaluation job in us-west-2, not us-east-1.",
        session_id="s1",
    )
    memory.add_turn(
        "user",
        "Correction: for long batch summaries, prefer qwen3:32b instead of qwen3:8b.",
        session_id="s1",
    )

    region = memory.search_episodes("Which region should the nightly evaluation job use?", n=5)
    model = memory.search_episodes("Which model should handle long batch summaries?", n=5)

    assert region
    assert "us-west-2" in region[0].text
    assert "us-east-1" not in region[0].text
    assert model
    assert "qwen3:32b" in model[0].text
    assert "qwen3:8b" not in model[0].text


def test_search_episodes_handles_sandbox_policy_language() -> None:
    memory = ProjectMemory(session_id="s1")

    memory.store_episode(
        "Decision: sandbox command execution through docker when available.",
        importance=0.9,
    )

    results = memory.search_episodes(
        "How should command execution be sandboxed when possible?", n=5
    )

    assert results
    assert "docker" in results[0].text.lower()
