"""External grader for the Engram boundary target at commit 7d37920.

These regressions were derived from fixes committed after the target. They are
expected to fail 3/3 when ``engram`` is imported from the target and pass 3/3
when imported from corrected reference commit 8e2e9e5 or a descendant.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from engram import MemoryTrustPolicy, ProjectMemory


def _metadata(**overrides: str) -> dict[str, str]:
    return {
        "tenant": "acme",
        "source": "operator",
        "writer": "admin",
        "trust": "verified",
        **overrides,
    }


def _policy() -> MemoryTrustPolicy:
    return MemoryTrustPolicy(
        tenant_id="acme",
        allowed_sources=frozenset({"operator"}),
        allowed_writers=frozenset({"admin"}),
    )


def test_storage_identifiers_cannot_escape_their_roots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="single path component"):
        ProjectMemory(base_dir=tmp_path / "projects", project_id="../escape")

    memory = ProjectMemory(base_dir=tmp_path / "sessions", project_id="safe")
    with pytest.raises(ValueError, match="single path component"):
        memory.new_session("nested/session")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_persistent_memory_paths_are_private(tmp_path: Path) -> None:
    previous_umask = os.umask(0o022)
    try:
        base_dir = tmp_path / "memory"
        memory = ProjectMemory(base_dir=base_dir, project_id="private", session_id="s1")
        memory.add_turn("user", "Remember my private preference.", session_id="s1")
        memory.close()
    finally:
        os.umask(previous_umask)

    project = base_dir / "private"
    assert stat.S_IMODE(project.stat().st_mode) == 0o700
    assert stat.S_IMODE((project / "sessions").stat().st_mode) == 0o700
    assert stat.S_IMODE((project / "sessions" / "s1.jsonl").stat().st_mode) == 0o600


def test_cross_tenant_episode_deletion_is_rejected(tmp_path: Path) -> None:
    unguarded = ProjectMemory(base_dir=tmp_path, project_id="p")
    episode_id = unguarded.store_episode(
        "Other tenant fact",
        metadata=_metadata(tenant="other"),
        bypass_filter=True,
    )
    unguarded.close()

    guarded = ProjectMemory(base_dir=tmp_path, project_id="p", trust_policy=_policy())

    assert guarded.delete_episode(episode_id) is False
    assert any(episode["id"] == episode_id for episode in guarded._episodes)
    assert guarded.get_trust_audit()[-1] == {
        "stage": "deletion",
        "action": "reject",
        "reasons": ["tenant_mismatch"],
        "episode_id": episode_id,
    }
