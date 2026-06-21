from __future__ import annotations

from agent_lib import LocalTool, LocalToolRuntime, ToolCall, WorkspacePolicy
from agent_lib.coordination import (
    ExternalAgentSession,
    ExternalAgentTeam,
    build_coordinator_tool_runtime,
    build_session_tool_runtime,
    route_by_capability,
)
from agent_lib.programming import EnforcingToolRuntime


def _tools() -> LocalToolRuntime:
    return LocalToolRuntime(
        [
            LocalTool("read_file", "read", lambda path: f"read:{path}"),
            LocalTool("replace_text", "replace", lambda path, old, new: f"replace:{path}"),
            LocalTool("retrieve", "retrieve", lambda query: f"retrieve:{query}"),
            LocalTool("compute", "compute", lambda expression: expression),
        ]
    )


def test_tool_grant_precedes_path_policy_and_none_preserves_behavior(tmp_path) -> None:
    granted = EnforcingToolRuntime(
        _tools(),
        WorkspacePolicy(root=str(tmp_path), allowed_tools=["read_file"]),
        root=tmp_path,
    )
    assert granted.invoke(ToolCall(name="read_file", arguments={"path": "input.txt"})).success is True

    denied = granted.invoke(ToolCall(name="replace_text", arguments={"path": "input.txt", "old": "a", "new": "b"}))
    assert denied.success is False
    assert denied.meta["error"] == "tool_not_granted"

    unrestricted = EnforcingToolRuntime(
        _tools(),
        WorkspacePolicy(root=str(tmp_path), allowed_tools=None, writable_paths=["input.txt"]),
        root=tmp_path,
    )
    assert unrestricted.invoke(ToolCall(name="read_file", arguments={"path": "input.txt"})).success is True
    assert unrestricted.invoke(ToolCall(name="replace_text", arguments={"path": "input.txt", "old": "a", "new": "b"})).success is True


def test_routing_and_scoped_runtime_compose(tmp_path) -> None:
    fs_agent = ExternalAgentSession("fs_agent", "filesystem", capabilities=["read_file", "replace_text"])
    search_agent = ExternalAgentSession("search_agent", "retrieval", capabilities=["retrieve"])
    calc_agent = ExternalAgentSession("calc_agent", "compute", capabilities=["compute"])
    team = ExternalAgentTeam("control-plane", mentor=fs_agent, workers=[search_agent, calc_agent])

    assert route_by_capability(team, "retrieve") is search_agent
    assert route_by_capability(team, "compute") is calc_agent
    assert route_by_capability(team, "nonexistent") is None

    runtime = build_session_tool_runtime(
        search_agent, _tools(), WorkspacePolicy(root=str(tmp_path), writable_paths=["input.txt"]), root=str(tmp_path)
    )
    result = runtime.invoke(ToolCall(name="replace_text", arguments={"path": "input.txt", "old": "a", "new": "b"}))
    assert result.success is False
    assert result.meta["error"] == "tool_not_granted"


def test_coordinator_runtime_empty_grant_denies_every_tool(tmp_path) -> None:
    coordinator = ExternalAgentSession("coord", "coordinator")
    runtime = build_coordinator_tool_runtime(coordinator, _tools(), WorkspacePolicy(root=str(tmp_path)), root=str(tmp_path))

    for call in (
        ToolCall(name="read_file", arguments={"path": "input.txt"}),
        ToolCall(name="replace_text", arguments={"path": "input.txt", "old": "a", "new": "b"}),
        ToolCall(name="run_command", arguments={"command": "echo no"}),
    ):
        result = runtime.invoke(call)
        assert result.success is False
        assert result.meta["error"] == "tool_not_granted"

    unrestricted = EnforcingToolRuntime(_tools(), WorkspacePolicy(root=str(tmp_path), allowed_tools=None), root=tmp_path)
    assert unrestricted.invoke(ToolCall(name="read_file", arguments={"path": "input.txt"})).success is True
