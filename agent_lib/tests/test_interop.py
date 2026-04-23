from __future__ import annotations

from agent_lib import (
    AgentAction,
    AgentRuntime,
    AgentTask,
    AgentContext,
    AgentObservation,
    ToolResult,
    LocalTool,
    LocalToolRuntime,
    SequencePlanner,
    describe_agent_runtime,
    describe_tool_runtime,
    run_to_interop_events,
    run_to_operation_result,
)
from agent_lib.runtime import InspectorTraceEmitter


def test_runtime_describes_agent_capability() -> None:
    runtime = AgentRuntime(
        planner=SequencePlanner([AgentAction.final("done")]),
        tool_runtime=LocalToolRuntime([]),
    )
    descriptor = describe_agent_runtime(runtime)
    assert descriptor.kind == "agent_runtime"
    assert "trace_events" in descriptor.features
    assert descriptor.metadata["tool_count"] == 0


def test_tool_runtime_describes_tool_provider_capability() -> None:
    tools = LocalToolRuntime([
        LocalTool(name="echo", description="Echo the text.", handler=lambda text: text),
    ])
    descriptor = describe_tool_runtime(tools)
    assert descriptor.kind == "tool_provider"
    assert descriptor.metadata["tool_names"] == ["echo"]


def test_run_exports_shared_events_and_operation_result() -> None:
    runtime = AgentRuntime(
        planner=SequencePlanner([
            AgentAction.tool("echo", {"text": "hello"}, message="Use the tool."),
            AgentAction.final("done"),
        ]),
        tool_runtime=LocalToolRuntime([
            LocalTool(name="echo", description="Echo the text.", handler=lambda text: text),
        ]),
    )
    run = runtime.run(AgentTask(task_id="agent-1", goal="Echo hello."))

    events = run_to_interop_events(run)
    event_types = [event.event_type for event in events]
    assert event_types[0] == "agent_run_started"
    assert "agent_action_selected" in event_types
    assert "agent_tool_invoked" in event_types
    assert "agent_tool_result" in event_types
    assert event_types[-1] == "agent_run_finished"

    result = run_to_operation_result(run)
    assert result.ok is True
    assert result.value["summary"]["status"] == "completed"
    assert result.value["summary"]["step_count"] == 2
    assert result.diagnostics["event_count"] >= len(events)



def test_trace_emitter_surfaces_execution_status_in_agent_summary():
    from agent_lib.programming import WorkspacePolicy, ProgrammingToolRuntime

    task = AgentTask(task_id="t1", goal="Run a blocked command", context={"workspace_policy": {"root": ".", "approval_mode": "auto", "isolation_mode": "workspace", "writable_paths": [], "runnable_commands": [], "command_isolation_backend": "docker", "command_isolation_fallback_to_host": True}})
    context = AgentContext(task=task, steps=[], recalled=[], tool_specs=[], active_controller="planner", escalated=False)
    action = AgentAction.tool("run_command", {"command": "rm -rf /"})
    result = ToolResult(name="run_command", output="Denied", success=False, meta={"error": "command_denied", "approval_required": True, "sandbox_requested_backend": "docker", "sandbox_backend": "host", "sandbox_fallback_used": True})
    observation = AgentObservation(kind="tool_result", text="Denied", tool_result=result, meta=dict(result.meta))
    trace = InspectorTraceEmitter().emit_step(context=context, action=action, observation=observation)
    summary = trace.context.signals["agent_summary"]
    assert summary["blocked_count"] == 1
    assert summary["degraded_count"] == 1
    assert summary["approval_count"] == 1
    assert summary["execution_modes"][0]["tool_name"] == "run_command"
