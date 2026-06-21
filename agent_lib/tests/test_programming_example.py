from __future__ import annotations

from pathlib import Path

from agent_lib.examples import FileWorkspace, make_programming_demo_runtime, run_programming_demo
from agent_lib import AgentTask


def test_programming_demo_updates_file_and_records_traces(tmp_path: Path) -> None:
    run, root = run_programming_demo(root=tmp_path, memory_backend="engram")

    assert run.status == "completed"
    assert "returns a + b" in (run.final_output or "")
    assert (root / "main.py").read_text(encoding="utf-8").strip().endswith("return a + b")
    assert run.escalations == 1
    assert len(run.steps) == 8
    assert run.steps[1].observation is not None
    assert "return a - b" in run.steps[1].observation.text
    assert run.steps[3].observation is not None
    assert run.steps[3].observation.text == "False"
    assert run.steps[6].observation is not None
    assert run.steps[6].observation.text == "True"
    assert all(step.trace is not None for step in run.steps)
    assert run.steps[1].trace is not None and run.steps[1].trace.metrics.engine == "executor"
    assert run.steps[4].trace is not None and run.steps[4].trace.metrics.engine == "critic"
    assert run.steps[-1].trace is not None and run.steps[-1].trace.metrics.engine == "critic"


def test_programming_demo_memory_recall_surfaces_prior_steps(tmp_path: Path) -> None:
    workspace = FileWorkspace(tmp_path)
    workspace.write_text("main.py", "def add(a, b):\n    return a - b\n")
    runtime = make_programming_demo_runtime(
        workspace,
        memory_backend="engram",
        memory_base_dir=tmp_path / ".agent_memory",
        session_id="agent_programming_demo",
    )

    run = runtime.run(
        AgentTask(
            task_id="fix_add_function",
            goal="Fix the add(a, b) implementation in main.py so it returns the sum.",
            session_id="agent_programming_demo",
            context={"path": "main.py"},
        )
    )

    assert run.status == "completed"
    assert len(run.steps) >= 3
    third_trace = run.steps[2].trace
    assert third_trace is not None
    sections = {section.title: section.text for section in third_trace.context.sections}
    assert "Memory" in sections
    assert "Inspect the buggy implementation" in sections["Memory"]
    assert "return a - b" in sections["Memory"]


def test_programming_demo_escalates_only_after_failed_local_check(tmp_path: Path) -> None:
    run, root = run_programming_demo(root=tmp_path, memory_backend="engram")

    assert run.status == "completed"
    assert run.escalations == 1
    assert (root / "main.py").read_text(encoding="utf-8").strip().endswith("return a + b")
    assert run.steps[3].observation is not None
    assert run.steps[3].observation.tool_result is not None
    assert run.steps[3].observation.tool_result.success is False
    critic_steps = [step for step in run.steps if step.trace is not None and step.trace.metrics.engine == "critic"]
    assert critic_steps
    assert "mentor" in (critic_steps[0].trace.metrics.model or "")
