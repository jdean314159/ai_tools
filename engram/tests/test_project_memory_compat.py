from __future__ import annotations

from types import SimpleNamespace

from engram import ProjectMemory


def test_build_prompt_includes_recent_working_turns() -> None:
    memory = ProjectMemory(session_id="s1")
    memory.add_turn("user", "Hola", session_id="s1")
    memory.add_turn("assistant", "¿Cómo estás?", session_id="s1")

    result = memory.build_prompt("Cuéntame más.")

    assert "Hola" in result["prompt"]
    assert "¿Cómo estás?" in result["prompt"]
    assert result["memory_tokens"] >= 2


def test_minimal_episode_and_stats_api_for_app_integrations() -> None:
    memory = ProjectMemory(session_id="s1")
    episode_id = memory.store_episode(
        text="Session summary: practiced greetings.",
        metadata={"type": "session_summary"},
        importance=0.95,
    )

    results = memory.search_episodes("summary", n=5, min_importance=0.5)
    stats = memory.get_stats()

    assert episode_id
    assert results
    assert hasattr(results[0], "text")
    assert stats["backend"] == "engram_lite"
    assert stats["episodic"]["count"] >= 1
