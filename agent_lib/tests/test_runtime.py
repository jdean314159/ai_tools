from __future__ import annotations

from agent_lib import (
    AgentAction,
    AgentRuntime,
    AgentTask,
    EngineRoles,
    LocalTool,
    LocalToolRuntime,
    SequencePlanner,
    ToolResult,
)


def test_runtime_invokes_tool_and_returns_final_output() -> None:
    planner = SequencePlanner(
        [
            AgentAction.tool("add", {"a": 2, "b": 3}, message="Need arithmetic."),
            AgentAction.final("The answer is 5."),
        ]
    )
    runtime = AgentRuntime(
        planner=planner,
        tool_runtime=LocalToolRuntime(
            [
                LocalTool(
                    name="add",
                    description="Add two integers.",
                    handler=lambda a, b: a + b,
                )
            ]
        ),
        engine_roles=EngineRoles(planner="mentor", executor="worker"),
    )

    run = runtime.run(AgentTask(task_id="sum", goal="Add 2 and 3.", session_id="agent_demo"))

    assert run.status == "completed"
    assert run.final_output == "The answer is 5."
    assert len(run.steps) == 2
    assert run.steps[0].observation is not None
    assert run.steps[0].observation.text == "5"
    assert run.steps[0].trace is not None
    assert run.steps[0].trace.metrics.engine == "executor"
    assert run.steps[1].trace is not None
    assert run.steps[1].trace.metrics.engine == "planner"


def test_runtime_escalates_to_critic_after_failed_tool_result() -> None:
    planner = SequencePlanner(
        [
            AgentAction.tool("check", message="Run the local verification."),
        ]
    )
    critic = SequencePlanner(
        [
            AgentAction.message_only("Escalating to the mentor after failure.", meta={"engine_role": "critic"}),
            AgentAction.final("Mentor fixed the issue.", meta={"engine_role": "critic"}),
        ]
    )
    runtime = AgentRuntime(
        planner=planner,
        critic=critic,
        tool_runtime=LocalToolRuntime(
            [
                LocalTool(
                    name="check",
                    description="Fail the local check.",
                    handler=lambda: ToolResult(name="check", output="False", success=False, meta={"reason": "mismatch"}),
                )
            ]
        ),
        engine_roles=EngineRoles(planner="worker", executor="worker", critic="mentor"),
    )

    run = runtime.run(AgentTask(task_id="verify", goal="Verify the patch.", session_id="agent_demo"), max_steps=4)

    assert run.status == "completed"
    assert run.stop_reason == "critic_completed"
    assert run.final_output == "Mentor fixed the issue."
    assert run.escalations == 1
    assert len(run.steps) == 3
    assert run.steps[0].observation is not None and run.steps[0].observation.tool_result is not None
    assert run.steps[0].observation.tool_result.success is False
    assert run.steps[1].trace is not None
    assert run.steps[1].trace.metrics.engine == "critic"
    assert run.steps[2].trace is not None
    assert run.steps[2].trace.metrics.engine == "critic"
