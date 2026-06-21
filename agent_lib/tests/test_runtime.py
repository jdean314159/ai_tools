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


def test_runtime_does_not_escalate_on_worker_self_report_without_objective_signal() -> None:
    planner = SequencePlanner(
        [
            AgentAction.message_only("I need mentor help, but no verifier failed."),
            AgentAction.final("Worker finished without critic."),
        ]
    )
    critic = SequencePlanner([AgentAction.final("Critic should not run.")])
    runtime = AgentRuntime(
        planner=planner,
        critic=critic,
        tool_runtime=LocalToolRuntime([]),
        engine_roles=EngineRoles(planner="worker", critic="mentor"),
    )

    run = runtime.run(
        AgentTask(task_id="self_report", goal="Do not escalate on self-report."),
        max_steps=3,
    )

    assert run.status == "completed"
    assert run.stop_reason == "completed"
    assert run.final_output == "Worker finished without critic."
    assert run.escalations == 0
    assert all(step.trace is not None and step.trace.metrics.engine != "critic" for step in run.steps)


def test_runtime_counts_but_does_not_cap_repeated_critic_escalations() -> None:
    planner = SequencePlanner(
        [
            AgentAction.tool("check", message="First objective verification."),
            AgentAction.tool("check", message="Second objective verification."),
            AgentAction.tool("check", message="Third objective verification."),
        ]
    )
    critic = SequencePlanner(
        [
            AgentAction.message_only("Return to worker.", meta={"handoff": "planner"}),
            AgentAction.message_only("Return to worker again.", meta={"handoff": "planner"}),
            AgentAction.final("Critic eventually stops the run."),
        ]
    )
    runtime = AgentRuntime(
        planner=planner,
        critic=critic,
        tool_runtime=LocalToolRuntime(
            [
                LocalTool(
                    name="check",
                    description="Always fail objective verification.",
                    handler=lambda: ToolResult(name="check", output="failed", success=False),
                )
            ]
        ),
        engine_roles=EngineRoles(planner="worker", executor="worker", critic="mentor"),
    )

    run = runtime.run(
        AgentTask(task_id="uncapped", goal="Show escalation counting without cap."),
        max_steps=8,
    )

    assert run.status == "completed"
    assert run.stop_reason == "critic_completed"
    assert run.escalations == 3


def test_runtime_critic_contract_is_implicit_planner_takeover_not_typed_feedback() -> None:
    planner = SequencePlanner([AgentAction.tool("check")])
    critic = SequencePlanner(
        [
            AgentAction.message_only("Free-text mentor guidance is accepted as a normal action."),
            AgentAction.final("Done by critic."),
        ]
    )
    runtime = AgentRuntime(
        planner=planner,
        critic=critic,
        tool_runtime=LocalToolRuntime(
            [
                LocalTool(
                    name="check",
                    description="Fail verification.",
                    handler=lambda: ToolResult(name="check", output="failed", success=False),
                )
            ]
        ),
    )

    run = runtime.run(AgentTask(task_id="critic_contract", goal="Inspect critic contract."), max_steps=4)

    assert run.status == "completed"
    assert run.stop_reason == "critic_completed"
    assert run.steps[1].action.kind == "message"
    assert "feedback_type" not in run.steps[1].action.meta
