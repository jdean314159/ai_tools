from __future__ import annotations

from pathlib import Path

from engram import ProjectMemory


def test_recent_turns_and_episodes_persist_across_reopen(tmp_path: Path) -> None:
    base_dir = tmp_path / "lite_memory"

    first = ProjectMemory(base_dir=base_dir, project_id="spanish_tutor", session_id="resume_s1")
    first.add_turn("user", "Hola, estoy aprendiendo español.", session_id="resume_s1")
    first.add_turn("assistant", "Corrección: estoy aprendiendo español.", session_id="resume_s1")
    episode_id = first.store_episode(
        text="Session summary: practiced greetings and present tense.",
        metadata={"type": "session_summary"},
        importance=0.95,
    )
    first.close()

    second = ProjectMemory(base_dir=base_dir, project_id="spanish_tutor", session_id="resume_s1")
    turns = second.get_recent_turns("resume_s1", limit=10)
    episodes = second.search_episodes("session summary", n=5, min_importance=0.5)

    assert episode_id
    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert "aprendiendo español" in turns[0]["text"]
    assert episodes
    assert "practiced greetings" in episodes[0].text
