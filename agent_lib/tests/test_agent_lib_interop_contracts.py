from __future__ import annotations

import sys

from agent_lib import (
    AgentAction,
    AgentRuntime,
    AgentTask,
    LocalTool,
    ToolCall,
    LocalToolRuntime,
    ToolResult,
    WorkspacePolicy,
    SequencePlanner,
    describe_agent_runtime,
    describe_tool_runtime,
    run_to_interop_events,
    run_to_memory_records,
    run_to_operation_result,
    tool_result_to_operation_result,
)
from agent_lib.programming import ProgrammingToolRuntime, execute_workspace_command


def _build_runtime(*, failing: bool = False) -> AgentRuntime:
    def echo(text: str) -> str:
        if failing:
            raise RuntimeError("boom")
        return text

    return AgentRuntime(
        planner=SequencePlanner([
            AgentAction.tool("echo", {"text": "hello"}, message="Use the tool."),
            AgentAction.final("done"),
        ]),
        tool_runtime=LocalToolRuntime([
            LocalTool(name="echo", description="Echo the text.", handler=echo),
        ]),
    )


def test_runtime_describes_agent_capability() -> None:
    runtime = AgentRuntime(
        planner=SequencePlanner([AgentAction.final("done")]),
        tool_runtime=LocalToolRuntime([]),
    )
    descriptor = describe_agent_runtime(runtime)
    assert descriptor.kind == "agent_runtime"
    assert "trace_events" in descriptor.features
    assert "memory_records" in descriptor.features
    assert descriptor.metadata["tool_count"] == 0
    assert runtime.get_capability_descriptor().provider == "agent_lib"


def test_tool_runtime_describes_tool_provider_capability() -> None:
    tools = LocalToolRuntime([
        LocalTool(name="echo", description="Echo the text.", handler=lambda text: text),
    ])
    descriptor = describe_tool_runtime(tools)
    assert descriptor.kind == "tool_provider"
    assert "operation_results" in descriptor.features
    assert descriptor.metadata["tool_names"] == ["echo"]
    assert tools.get_capability_descriptor().provider == "agent_lib"


def test_run_exports_shared_events_memory_records_and_operation_result() -> None:
    runtime = _build_runtime()
    run = runtime.run(AgentTask(task_id="agent-1", goal="Echo hello."))

    events = run_to_interop_events(run)
    event_types = [event.event_type for event in events]
    assert event_types[0] == "agent_run_started"
    assert "agent_action_selected" in event_types
    assert "agent_tool_invoked" in event_types
    assert "agent_tool_result" in event_types
    assert event_types[-1] == "agent_run_finished"

    records = run_to_memory_records(run)
    assert records[0].source == "agent_lib.task"
    assert any(record.source == "agent_lib.observation" for record in records)

    result = run_to_operation_result(run, runtime=runtime)
    assert result.ok is True
    assert result.value["summary"]["status"] == "completed"
    assert result.value["summary"]["step_count"] == 2
    assert result.diagnostics["event_count"] >= len(events)
    assert result.diagnostics["trace_events"]
    assert result.diagnostics["memory_records"]
    assert result.diagnostics["capability"].provider == "agent_lib"


def test_runtime_run_interop_returns_shared_contracts() -> None:
    runtime = _build_runtime()
    result = runtime.run_interop(AgentTask(task_id="agent-2", goal="Echo hello."))
    assert result.ok is True
    assert result.value["summary"]["status"] == "completed"
    assert result.diagnostics["trace_events"]
    assert result.diagnostics["memory_records"]
    assert result.diagnostics["capability"].component == "AgentRuntime"


def test_tool_runtime_invoke_interop_returns_warning_for_failure() -> None:
    runtime = _build_runtime(failing=True).tool_runtime
    result = runtime.invoke_interop(type("Call", (), {"name": "echo", "arguments": {"text": "hello"}})())
    assert result.ok is True
    assert result.value["success"] is False
    assert result.warnings
    assert result.warnings[0].code == "tool_invocation_failed"
    assert result.diagnostics["capability"].component == "LocalToolRuntime"


def test_agent_run_failure_warning_is_surfaced_in_operation_result() -> None:
    runtime = _build_runtime(failing=True)
    run = runtime.run(AgentTask(task_id="agent-3", goal="Echo hello."), max_steps=2)
    result = run_to_operation_result(run, runtime=runtime)
    warning_codes = {warning.code for warning in result.warnings}
    assert "agent_tool_failure" in warning_codes


def test_programming_tool_runtime_invoke_interop_surfaces_blocked_command() -> None:
    runtime = ProgrammingToolRuntime(inner=LocalToolRuntime([]), workspace=WorkspacePolicy(root='.', runnable_commands=[]), root='.')
    result = runtime.invoke_interop(type('Call', (), {'name': 'run_command', 'arguments': {'command': 'echo nope'}})())
    assert result.ok is True
    assert 'tool_execution_blocked' in {warning.code for warning in result.warnings}
    assert result.value['execution_state']['blocked'] is True
    assert result.diagnostics['capability'].component == 'ProgrammingToolRuntime'


def test_execute_workspace_command_interop_surfaces_degraded_fallback(tmp_path, monkeypatch) -> None:
    import agent_lib.programming as programming_module
    command = f"{sys.executable} -c 'print(\"fallback\")'"
    policy = WorkspacePolicy(root=str(tmp_path), runnable_commands=[command], command_isolation_backend='auto', command_isolation_fallback_to_host=True)
    monkeypatch.setattr(programming_module.shutil, 'which', lambda name: None)
    tool_result = execute_workspace_command(tmp_path, command, workspace_policy=policy)
    interop = tool_result_to_operation_result(tool_result, call=ToolCall(name='run_command', arguments={'command': command}))
    assert 'tool_execution_degraded' in {warning.code for warning in interop.warnings}
    assert interop.value['execution_state']['degraded'] is True
    assert interop.diagnostics['execution_state']['sandbox_backend'] == 'host'


def test_run_interop_aggregates_execution_mode_signals() -> None:
    planner = SequencePlanner([AgentAction.tool('approve', {'path': 'a.txt'}, message='Patch it.'), AgentAction.final('done')])
    class _ApprovalRuntime(LocalToolRuntime):
        def invoke(self, call):
            return ToolResult(name=call.name, output='Approval required', success=True, meta={'approval_required': True, 'approval_mode': 'human_checkpoint', 'patch_status': 'proposed'})
    runtime = AgentRuntime(planner=planner, tool_runtime=_ApprovalRuntime([]))
    result = runtime.run_interop(AgentTask(task_id='agent-approve', goal='Patch file.'))
    assert result.ok is True
    assert result.diagnostics['approval_actions']
    assert 'tool_approval_required' in {warning.code for warning in result.warnings}
