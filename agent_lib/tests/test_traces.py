from __future__ import annotations

from agent_lib import AgentAction, AgentRuntime, AgentTask, LocalToolRuntime, SequencePlanner


def test_trace_emitter_produces_llm_inspector_trace_objects() -> None:
    runtime = AgentRuntime(
        planner=SequencePlanner([AgentAction.final("All done.")]),
        tool_runtime=LocalToolRuntime([]),
    )
    run = runtime.run(AgentTask(task_id="trace", goal="Finish the task."))

    assert len(run.steps) == 1
    trace = run.steps[0].trace
    assert trace is not None
    assert trace.turn.text == "Finish the task."
    assert trace.context.sections[0].title == "Task"
    assert trace.events[0].kind == "agent_action_selected"


def test_trace_emitter_carries_active_optimizations_from_action_meta() -> None:
    runtime = AgentRuntime(
        planner=SequencePlanner(
            [
                AgentAction.final(
                    "Done.",
                    meta={
                        "active_optimizations": [
                            {
                                "kind": "speculative_decoding",
                                "backend": "demo",
                                "parameters": {"speculative_tokens": 5},
                            },
                            {
                                "kind": "kv_cache_compression",
                                "backend": "demo",
                                "parameters": {"mode": "turboquant", "bits": 4},
                            },
                        ]
                    },
                )
            ]
        ),
        tool_runtime=LocalToolRuntime([]),
    )
    run = runtime.run(AgentTask(task_id="opt", goal="Finish with optimization metadata."))

    trace = run.steps[0].trace
    assert trace is not None
    assert [item["kind"] for item in trace.metrics.inference_optimizations] == [
        "speculative_decoding",
        "kv_cache_compression",
    ]
