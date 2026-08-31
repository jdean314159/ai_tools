from __future__ import annotations

from agent_lib import (
    AgentAction,
    AgentContext,
    AgentRuntime,
    AgentTask,
    EngramLiteMemoryAdapter,
    LocalToolRuntime,
)
from engram import ProjectMemory


class RecordingPlanner:
    def __init__(self) -> None:
        self.contexts: list[AgentContext] = []
        self._step = 0

    def plan(self, context: AgentContext) -> AgentAction:
        self.contexts.append(context)
        self._step += 1
        if self._step == 1:
            return AgentAction.message_only("Remember: greet the user politely.")
        return AgentAction.final("Done.")


def test_engram_memory_adapter_replays_previous_step_as_evidence(tmp_path) -> None:
    memory = ProjectMemory(
        base_dir=tmp_path / "memory", project_id="agent_demo", session_id="agent_s1"
    )
    planner = RecordingPlanner()
    runtime = AgentRuntime(
        planner=planner,
        tool_runtime=LocalToolRuntime([]),
        memory=EngramLiteMemoryAdapter(memory),
    )

    run = runtime.run(
        AgentTask(task_id="demo", goal="Say hello.", session_id="agent_s1"), max_steps=2
    )

    assert run.status == "completed"
    assert len(planner.contexts) == 2
    second_context = planner.contexts[1]
    assert second_context.recalled
    assert any("greet the user politely" in item.text for item in second_context.recalled)
    assert second_context.memory_trace is not None
    assert second_context.memory_trace.metrics.engine == "engram"
    assert second_context.memory_trace.events[0].kind == "agent_memory_recall"
