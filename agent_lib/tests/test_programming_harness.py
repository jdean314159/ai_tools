from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import agent_lib.programming as programming_module

from agent_lib import (
    ToolCall,
    AgentAction,
    AgentRuntime,
    AgentTask,
    LocalTool,
    LocalToolRuntime,
    SequencePlanner,
    WorkspacePolicy,
)
from agent_lib.programming import (
    ProgrammingToolRuntime,
    WorkspaceIsolationManager,
    execute_workspace_command,
)
from agent_lib.examples import FileWorkspace, make_programming_tool_runtime, resume_programming_demo, run_programming_demo




def test_execute_workspace_command_scrubs_environment_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LIB_SECRET", "super-secret")
    command = f"{sys.executable} -c 'import os; print(os.getenv(\"AGENT_LIB_SECRET\", \"missing\"))'"

    result = execute_workspace_command(tmp_path, command)

    assert result.success is True
    assert str(result.output).strip() == "missing"
    assert "AGENT_LIB_SECRET" not in result.meta.get("environment_keys", [])
    assert result.meta.get("environment_inherited") is False


def test_execute_workspace_command_allows_selected_environment_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LIB_SECRET", "super-secret")
    command = f"{sys.executable} -c 'import os; print(os.getenv(\"AGENT_LIB_SECRET\", \"missing\"))'"
    policy = WorkspacePolicy(
        root=str(tmp_path),
        runnable_commands=[command],
        inherit_environment=False,
        allowed_environment_keys=["PATH", "AGENT_LIB_SECRET"],
    )

    result = execute_workspace_command(tmp_path, command, workspace_policy=policy)

    assert result.success is True
    assert str(result.output).strip() == "super-secret"
    assert "AGENT_LIB_SECRET" in result.meta.get("environment_keys", [])


def test_execute_workspace_command_times_out_and_reports_metadata(tmp_path: Path) -> None:
    command = f'{sys.executable} -c "import time; time.sleep(1.0)"'
    policy = WorkspacePolicy(
        root=str(tmp_path),
        runnable_commands=[command],
        command_timeout_seconds=0.1,
    )

    result = execute_workspace_command(tmp_path, command, workspace_policy=policy)

    assert result.success is False
    assert result.meta.get("error") == "command_timeout"
    assert result.meta.get("timeout_seconds") == 0.1
    assert "timed out" in str(result.output).lower()


def test_execute_workspace_command_truncates_large_output(tmp_path: Path) -> None:
    command = f"{sys.executable} -c 'print(\"x\" * 600)'"
    policy = WorkspacePolicy(
        root=str(tmp_path),
        runnable_commands=[command],
        max_command_output_chars=256,
    )

    result = execute_workspace_command(tmp_path, command, workspace_policy=policy)

    assert result.success is True
    assert result.meta.get("stdout_truncated") is True
    assert result.meta.get("stdout_length", 0) > 256
    assert "[output truncated]" in result.meta.get("stdout", "")


class _FakePopen:
    last_argv = None
    last_kwargs = None

    def __init__(self, argv, **kwargs):
        type(self).last_argv = list(argv)
        type(self).last_kwargs = dict(kwargs)
        self.returncode = 0
        self.pid = 4242

    def communicate(self, timeout=None):
        return ("sandbox-ok\n", "")


def test_execute_workspace_command_uses_docker_backend_when_configured(tmp_path: Path, monkeypatch) -> None:
    command = "python -c 'print(123)'"
    policy = WorkspacePolicy(
        root=str(tmp_path),
        runnable_commands=[command],
        command_isolation_backend="docker",
        command_isolation_image="python:3.12-slim",
    )

    monkeypatch.setattr(programming_module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(programming_module.subprocess, "Popen", _FakePopen)

    result = execute_workspace_command(tmp_path, command, workspace_policy=policy)

    assert result.success is True
    assert result.meta.get("sandbox_backend") == "docker"
    assert result.meta.get("sandbox_external") is True
    argv = _FakePopen.last_argv
    assert argv is not None
    assert argv[:3] == ["docker", "run", "--rm"]
    assert "python:3.12-slim" in argv
    assert "/bin/sh" in argv
    assert result.meta.get("sandbox_command") == argv


def test_execute_workspace_command_reports_unavailable_explicit_sandbox(tmp_path: Path, monkeypatch) -> None:
    command = "python -c 'print(123)'"
    policy = WorkspacePolicy(
        root=str(tmp_path),
        runnable_commands=[command],
        command_isolation_backend="docker",
        command_isolation_fallback_to_host=False,
    )

    monkeypatch.setattr(programming_module.shutil, "which", lambda name: None)

    result = execute_workspace_command(tmp_path, command, workspace_policy=policy)

    assert result.success is False
    assert result.meta.get("error") == "sandbox_unavailable"
    assert result.meta.get("sandbox_requested_backend") == "docker"


def test_execute_workspace_command_can_fallback_to_host_when_requested(tmp_path: Path, monkeypatch) -> None:
    command = f"{sys.executable} -c 'print(\"host-fallback\")'"
    policy = WorkspacePolicy(
        root=str(tmp_path),
        runnable_commands=[command],
        command_isolation_backend="auto",
        command_isolation_fallback_to_host=True,
    )

    monkeypatch.setattr(programming_module.shutil, "which", lambda name: None)

    result = execute_workspace_command(tmp_path, command, workspace_policy=policy)

    assert result.success is True
    assert str(result.output).strip() == "host-fallback"
    assert result.meta.get("sandbox_backend") == "host"
    assert result.meta.get("sandbox_fallback_used") is True


def test_programming_demo_persists_task_state_and_plan(tmp_path: Path) -> None:
    run, root = run_programming_demo(root=tmp_path, memory_backend="engram_lite")

    assert run.status == "completed"
    state_path = root / ".agent_state" / "fix_add_function.json"
    assert state_path.exists()

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["current_step_id"] == "complete_task"
    assert payload["last_verification"]["success"] is True
    assert "main.py" in payload["touched_files"]
    plan = {item["step_id"]: item for item in payload["plan"]}
    assert plan["inspect_file"]["status"] == "completed"
    assert plan["apply_patch"]["status"] == "completed"
    assert plan["verify_patch"]["status"] == "failed"
    assert plan["repair_patch"]["status"] == "completed"
    assert plan["complete_task"]["status"] == "completed"


def test_programming_trace_includes_state_summary(tmp_path: Path) -> None:
    run, _ = run_programming_demo(root=tmp_path, memory_backend="engram_lite")

    trace = run.steps[1].trace
    assert trace is not None
    sections = {section.title: section.text for section in trace.context.sections}
    assert "Programming State" in sections
    assert "current_step=inspect_file" in sections["Programming State"]


def test_runtime_interrupts_repeated_identical_tool_calls() -> None:
    planner = SequencePlanner(
        [
            AgentAction.tool("noop", {"x": 1}, message="Again."),
            AgentAction.tool("noop", {"x": 1}, message="Again."),
            AgentAction.tool("noop", {"x": 1}, message="Again."),
        ]
    )
    runtime = AgentRuntime(
        planner=planner,
        tool_runtime=LocalToolRuntime([LocalTool(name="noop", description="Return ok.", handler=lambda x: f"ok:{x}")]),
        max_repeated_tool_calls=3,
    )

    run = runtime.run(AgentTask(task_id="repeat", goal="Repeat the same tool.", session_id="repeat"), max_steps=5)

    assert run.status == "stopped"
    assert run.stop_reason == "planner_stop"
    assert run.final_output == "Interrupted repeated tool call: noop"
    assert len(run.steps) == 2



def test_programming_context_budget_compacts_history_and_persists_large_output(tmp_path: Path) -> None:
    large_seed = "def add(a, b):\n    return a - b\n\n" + ("# filler line\n" * 80)
    run, root = run_programming_demo(root=tmp_path, memory_backend="engram_lite", seed_content=large_seed)

    trace = run.steps[-1].trace
    assert trace is not None
    sections = {section.title: section.text for section in trace.context.sections}
    assert "Context Budget" in sections
    assert "compacted_steps=" in sections["Context Budget"]

    artifact_dir = root / ".agent_state" / "context_artifacts"
    artifacts = sorted(artifact_dir.glob("*.txt"))
    assert artifacts, "expected at least one stored full-output artifact"
    assert "filler line" in artifacts[0].read_text(encoding="utf-8")


def test_programming_failure_policy_stops_on_empty_read_result(tmp_path: Path) -> None:
    run, root = run_programming_demo(root=tmp_path, memory_backend="engram_lite", seed_content="", max_steps=6)

    assert run.status == "stopped"
    assert run.final_output == "Stopped after empty result from read_file."
    payload = json.loads((root / ".agent_state" / "fix_add_function.json").read_text(encoding="utf-8"))
    assert payload["last_policy_decision"] in {None, ""} or isinstance(payload["last_policy_decision"], str)


def test_programming_demo_can_resume_from_persisted_state(tmp_path: Path) -> None:
    first_run, root = run_programming_demo(root=tmp_path, memory_backend="engram_lite", max_steps=2)

    assert first_run.status == "stopped"
    assert first_run.stop_reason == "max_steps"

    resumed_run, _ = resume_programming_demo(root=root, memory_backend="engram_lite", max_steps=12)

    assert resumed_run.status == "completed"
    state = json.loads((root / ".agent_state" / "fix_add_function.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["context_window_index"] >= 1
    assert state["step_count"] >= 1
    assert (root / "main.py").read_text(encoding="utf-8").strip().endswith("return a + b")


def test_programming_tool_runtime_blocks_writes_in_proposal_only_mode(tmp_path: Path) -> None:
    workspace = FileWorkspace(tmp_path)
    workspace.write_text("main.py", "def add(a, b):\n    return a - b\n")
    runtime = make_programming_tool_runtime(
        workspace,
        WorkspacePolicy(
            root=str(tmp_path),
            writable_paths=["main.py"],
            runnable_commands=[],
            approval_mode="proposal_only",
        ),
    )

    result = runtime.invoke(ToolCall(name="replace_text", arguments={"path": "main.py", "old": "return a - b", "new": "return a + b"}))

    assert result.success is True
    assert result.meta.get("approval_required") is True
    assert result.meta.get("patch_status") == "proposed"
    assert "return a - b" in workspace.read_text("main.py")


def test_programming_tool_runtime_default_denies_writes_when_allowlist_empty(tmp_path: Path) -> None:
    workspace = FileWorkspace(tmp_path)
    workspace.write_text("main.py", "def add(a, b):\n    return a - b\n")
    runtime = make_programming_tool_runtime(
        workspace,
        WorkspacePolicy(
            root=str(tmp_path),
            writable_paths=[],
            runnable_commands=[],
            approval_mode="auto",
        ),
    )

    result = runtime.invoke(ToolCall(name="replace_text", arguments={"path": "main.py", "old": "return a - b", "new": "return a + b"}))

    assert result.success is False
    assert result.meta.get("error") == "write_denied"
    assert "return a - b" in workspace.read_text("main.py")


def test_programming_tool_runtime_enforces_command_allowlist(tmp_path: Path) -> None:
    workspace = FileWorkspace(tmp_path)
    workspace.write_text("main.py", "def add(a, b):\n    return a + b\n")
    command = f"{__import__('sys').executable} -m py_compile main.py"
    runtime = make_programming_tool_runtime(
        workspace,
        WorkspacePolicy(
            root=str(tmp_path),
            writable_paths=["main.py"],
            runnable_commands=[command],
            approval_mode="auto",
        ),
    )

    allowed = runtime.invoke(ToolCall(name="run_command", arguments={"command": command}))
    denied = runtime.invoke(ToolCall(name="run_command", arguments={"command": "echo not-allowed"}))

    assert allowed.success is True
    assert allowed.meta.get("returncode") == 0
    assert denied.success is False
    assert denied.meta.get("error") == "command_denied"


def test_programming_tool_runtime_blocks_path_escape(tmp_path: Path) -> None:
    workspace = FileWorkspace(tmp_path)
    workspace.write_text("main.py", "def add(a, b):\n    return a - b\n")
    runtime = make_programming_tool_runtime(
        workspace,
        WorkspacePolicy(
            root=str(tmp_path),
            writable_paths=["main.py"],
            runnable_commands=[],
            approval_mode="auto",
        ),
    )

    result = runtime.invoke(ToolCall(name="read_file", arguments={"path": "../outside.py"}))

    assert result.success is False
    assert result.meta.get("error") == "path_escape"


def test_workspace_isolation_manager_creates_fallback_worktree_copy(tmp_path: Path) -> None:
    workspace_root = tmp_path / "repo"
    workspace_root.mkdir()
    (workspace_root / "main.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    state_root = workspace_root / ".agent_state"
    manager = WorkspaceIsolationManager(state_root)
    policy = WorkspacePolicy(root=str(workspace_root), writable_paths=["main.py"], runnable_commands=[], approval_mode="auto", isolation_mode="worktree")

    allocation = manager.prepare_workspace(workspace_root, "worker_a", policy)

    assert allocation.source == "copy"
    isolated_root = Path(allocation.root)
    assert isolated_root != workspace_root
    assert (isolated_root / "main.py").read_text(encoding="utf-8").strip().endswith("return a - b")


def test_programming_tool_runtime_enforces_patch_ownership(tmp_path: Path) -> None:
    workspace = FileWorkspace(tmp_path)
    workspace.write_text("main.py", "def add(a, b):\n    return a - b\n")
    state_root = tmp_path / ".agent_state"
    manager = WorkspaceIsolationManager(state_root)
    policy = WorkspacePolicy(root=str(tmp_path), writable_paths=["main.py"], runnable_commands=[], approval_mode="auto")

    runtime_a = make_programming_tool_runtime(workspace, policy, owner_id="worker_a", isolation_manager=manager)
    runtime_b = make_programming_tool_runtime(workspace, policy, owner_id="worker_b", isolation_manager=manager)

    first = runtime_a.invoke(ToolCall(name="replace_text", arguments={"path": "main.py", "old": "return a - b", "new": "return a + b"}))
    second = runtime_b.invoke(ToolCall(name="replace_text", arguments={"path": "main.py", "old": "return a + b", "new": "return a * b"}))

    assert first.success is True
    assert second.success is False
    assert second.meta.get("error") == "ownership_denied"

    release = manager.release_patch_lease("worker_a", ["main.py"])
    assert release.status == "released"

    third = runtime_b.invoke(ToolCall(name="replace_text", arguments={"path": "main.py", "old": "return a + b", "new": "return a * b"}))
    assert third.success is True
