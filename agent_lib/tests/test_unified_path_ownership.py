from __future__ import annotations

import json
from multiprocessing import get_context
from pathlib import Path

from agent_lib import (
    ExternalAgentSession,
    ExternalAgentTeam,
    InMemoryMailbox,
    LocalTool,
    LocalToolRuntime,
    ToolCall,
    WorkspacePolicy,
    build_managed_coordination,
)
from agent_lib.programming import ProgrammingToolRuntime, WorkspaceIsolationManager


def _race_for_lease(state_root: str, owner_id: str, queue) -> None:
    manager = WorkspaceIsolationManager(state_root)
    queue.put(manager.acquire_patch_lease(owner_id, ["shared.py"]).status)


def _replace_on_disk(path: str, old: str, new: str, *, root: Path) -> str:
    target = root / path
    target.write_text(target.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    return "replaced"


def test_patch_lease_acquisition_is_atomic_across_processes(tmp_path: Path) -> None:
    context = get_context("fork")
    queue = context.Queue()
    processes = [
        context.Process(target=_race_for_lease, args=(str(tmp_path), f"worker-{index}", queue))
        for index in range(3)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    statuses = [queue.get(timeout=2) for _ in processes]
    assert statuses.count("active") == 1
    assert statuses.count("denied") == 2


def test_managed_mailbox_reservation_is_the_enforced_lease_view(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "shared.py").write_text("before\n", encoding="utf-8")
    team = ExternalAgentTeam(
        project_id="ownership",
        mentor=ExternalAgentSession("mentor", "mentor"),
        workers=[
            ExternalAgentSession("agent-a", "worker", capabilities=["replace_text"]),
            ExternalAgentSession("agent-b", "worker", capabilities=["replace_text"]),
        ],
    )
    inner = LocalToolRuntime(
        [
            LocalTool(
                "replace_text",
                "replace",
                lambda path, old, new: _replace_on_disk(path, old, new, root=workspace),
            )
        ]
    )
    managed = build_managed_coordination(
        team,
        inner,
        WorkspacePolicy(root=str(workspace), writable_paths=["shared.py"]),
        root=str(workspace),
        state_root=str(tmp_path / "state"),
    )

    assert managed.coordinator.mailbox.isolation_manager is managed.isolation_manager
    assert all(
        runtime.isolation_manager is managed.isolation_manager
        for runtime in managed.worker_runtimes.values()
    )
    first = managed.coordinator.reserve_paths(
        "agent-a", ["shared.py"], thread_id="task", note="editing"
    )
    conflict = managed.coordinator.reserve_paths("agent-b", ["shared.py"])
    denied = managed.worker_runtimes["agent-b"].invoke(
        ToolCall("replace_text", {"path": "shared.py", "old": "before", "new": "after"})
    )

    assert first[0].status == "active"
    assert conflict[0].status == "conflict"
    assert conflict[0].metadata["current_holder"] == "agent-a"
    assert denied.success is False and denied.meta["error"] == "ownership_denied"
    assert (workspace / "shared.py").read_text(encoding="utf-8") == "before\n"


def test_managed_reservation_releases_and_canonicalizes_paths(tmp_path: Path) -> None:
    manager = WorkspaceIsolationManager(tmp_path / "state")
    mailbox = InMemoryMailbox(manager)
    assert mailbox.reserve_paths("agent-a", ["shared.py"])[0].status == "active"
    assert mailbox.reserve_paths("agent-b", ["sub/../shared.py"])[0].status == "conflict"
    assert mailbox.release_paths("agent-a", ["shared.py"])[0].status == "released"
    assert mailbox.release_paths("agent-a", ["shared.py"]) == []
    assert mailbox.reserve_paths("agent-b", ["shared.py"])[0].status == "active"


def test_same_owner_reacquire_preserves_reservation_scope(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "shared.py").write_text("before", encoding="utf-8")
    manager = WorkspaceIsolationManager(tmp_path / "state")
    mailbox = InMemoryMailbox(manager)
    reserved = mailbox.reserve_paths(
        "agent-a", ["shared.py"], thread_id="thread-a", note="keep this scope"
    )[0]
    runtime = ProgrammingToolRuntime(
        LocalToolRuntime(
            [
                LocalTool(
                    "replace_text",
                    "replace",
                    lambda path, old, new: _replace_on_disk(path, old, new, root=workspace),
                )
            ]
        ),
        WorkspacePolicy(root=str(workspace), writable_paths=["shared.py"]),
        root=workspace,
        owner_id="agent-a",
        isolation_manager=manager,
    )

    assert runtime.invoke(
        ToolCall("replace_text", {"path": "shared.py", "old": "before", "new": "after"})
    ).success
    reread = mailbox.active_reservations()[0]
    assert (reread.thread_id, reread.note, reread.created_at, reread.metadata) == (
        reserved.thread_id,
        reserved.note,
        reserved.created_at,
        reserved.metadata,
    )


def test_legacy_lease_record_has_unknown_timestamp_until_acquired(tmp_path: Path) -> None:
    manager = WorkspaceIsolationManager(tmp_path / "state")
    manager._leases_path.write_text(
        json.dumps({"shared.py": {"owner_id": "agent-a", "status": "active"}}), encoding="utf-8"
    )
    mailbox = InMemoryMailbox(manager)

    legacy = mailbox.active_reservations()[0]
    assert legacy.created_at is None
    assert legacy.thread_id == "default"
    manager.acquire_patch_lease("agent-a", ["shared.py"])
    assert mailbox.active_reservations()[0].created_at is not None


def test_no_manager_mailbox_remains_advisory() -> None:
    mailbox = InMemoryMailbox()
    assert mailbox.reserve_paths("agent-a", ["shared.py"])[0].status == "active"
    assert mailbox.reserve_paths("agent-b", ["shared.py"])[0].status == "conflict"
