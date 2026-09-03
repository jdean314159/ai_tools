from __future__ import annotations

from pathlib import Path
import os
import stat

import pytest

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


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_persistent_memory_paths_are_private(tmp_path: Path) -> None:
    base_dir = tmp_path / "memory"
    memory = ProjectMemory(base_dir=base_dir, project_id="private", session_id="s1")
    memory.add_turn("user", "Remember my private preference.", session_id="s1")
    memory.close()

    project = base_dir / "private"
    assert stat.S_IMODE(project.stat().st_mode) == 0o700
    assert stat.S_IMODE((project / "sessions").stat().st_mode) == 0o700
    assert stat.S_IMODE((project / "sessions" / "s1.jsonl").stat().st_mode) == 0o600
    assert stat.S_IMODE((project / "schema_version.json").stat().st_mode) == 0o600


@pytest.mark.parametrize("value", ["../escape", "/absolute", "nested/session", ".."])
def test_storage_identifiers_cannot_escape_their_roots(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="single path component"):
        ProjectMemory(base_dir=tmp_path, project_id=value)

    memory = ProjectMemory(base_dir=tmp_path, project_id="safe")
    with pytest.raises(ValueError, match="single path component"):
        memory.new_session(value)
