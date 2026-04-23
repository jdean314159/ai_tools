from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp

from ..coordination import CoordinationMessage, FileReservation
from .integration_mode import make_external_programming_team, make_external_session_coordinator
from .programming_task import FileWorkspace, run_programming_demo


@dataclass(frozen=True)
class IntegrationDemoResult:
    root: Path
    thread_id: str
    final_output: str
    messages: list[CoordinationMessage]
    reservations: list[FileReservation]


@dataclass(frozen=True)
class ModeComparisonResult:
    native_root: Path
    native_final_output: str
    integration: IntegrationDemoResult

class _WorkspaceHarness:
    def __init__(self, workspace: FileWorkspace) -> None:
        self.workspace = workspace

    def inspect(self, path: str) -> str:
        return self.workspace.read_text(path)

    def patch(self, path: str, old: str, new: str) -> str:
        return self.workspace.replace_text(path, old, new)

    def verify(self, path: str, expected: str) -> bool:
        return self.workspace.contains_text(path, expected)



def run_integration_programming_demo(
    *,
    root: str | Path | None = None,
    thread_id: str = "programming-task",
) -> tuple[IntegrationDemoResult, Path]:
    if root is None:
        root_path = Path(mkdtemp(prefix="agent_lib_integration_demo_"))
    else:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)

    workspace = FileWorkspace(root_path)
    workspace.write_text("main.py", "def add(a, b):\n    return a - b\n")
    tools = _WorkspaceHarness(workspace)

    team = make_external_programming_team(
        project_id="programming-demo",
        mentor_id="mentor",
        worker_ids=("worker",),
        scout_ids=("scout",),
    )
    coordinator = make_external_session_coordinator(team)

    mentor = team.mentor.agent_id
    worker = team.workers[0].agent_id
    scout = team.scouts[0].agent_id if team.scouts else worker

    coordinator.send(
        mentor,
        scout,
        kind="finding",
        subject="Inspect buggy file",
        body="Read main.py and summarize the bug before any edits.",
        thread_id=thread_id,
    )
    contents = tools.inspect("main.py")
    coordinator.send(
        scout,
        mentor,
        kind="finding",
        subject="Bug summary",
        body=f"main.py currently contains:\n{contents}\nThe function subtracts instead of adding.",
        thread_id=thread_id,
        metadata={"path": "main.py"},
    )

    reservations = coordinator.reserve_paths(worker, ["main.py"], thread_id=thread_id, note="Applying targeted patch")
    patch_note = tools.patch("main.py", "return a - b", "return a + b")
    coordinator.send(
        mentor,
        worker,
        kind="patch_proposal",
        subject="Apply minimal fix",
        body="Change the implementation from subtraction to addition and keep the patch narrow.",
        thread_id=thread_id,
        metadata={"path": "main.py"},
    )
    coordinator.send(
        worker,
        mentor,
        kind="patch_proposal",
        subject="Patch applied",
        body=f"{patch_note}. main.py now ends with `return a + b`.",
        thread_id=thread_id,
        metadata={"path": "main.py"},
    )

    verified = tools.verify("main.py", "return a + b")
    coordinator.send(
        worker,
        mentor,
        kind="verification_result",
        subject="Verification result",
        body="Local verification passed for main.py." if verified else "Local verification failed for main.py.",
        thread_id=thread_id,
        metadata={"path": "main.py", "success": verified},
    )
    released = coordinator.release_paths(worker, ["main.py"])
    coordinator.send(
        mentor,
        worker,
        kind="decision",
        subject="Task complete",
        body="Accepted the patch. The integration-mode team repaired add(a, b).",
        thread_id=thread_id,
        metadata={"accepted": verified},
    )

    messages = []
    for session in team.all_sessions:
        messages.extend(coordinator.inbox(session.agent_id, thread_id=thread_id))
    messages = sorted(messages, key=lambda item: item.created_at)

    result = IntegrationDemoResult(
        root=root_path,
        thread_id=thread_id,
        final_output="Accepted the patch. The integration-mode team repaired add(a, b).",
        messages=messages,
        reservations=[*reservations, *released],
    )
    return result, root_path



def run_mode_comparison_demo(
    *,
    root: str | Path | None = None,
    memory_backend: str = "engram_lite",
) -> ModeComparisonResult:
    base = Path(root) if root is not None else Path(mkdtemp(prefix="agent_lib_mode_compare_"))
    base.mkdir(parents=True, exist_ok=True)

    native_root = base / "native"
    native_run, native_root = run_programming_demo(root=native_root, memory_backend=memory_backend)

    integration_root = base / "integration"
    integration, _ = run_integration_programming_demo(root=integration_root)

    return ModeComparisonResult(
        native_root=native_root,
        native_final_output=str(native_run.final_output or ""),
        integration=integration,
    )
