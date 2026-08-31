#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent_lib import (
    AgentAction,
    AgentRuntime,
    AgentTask,
    EngineRoles,
    SequencePlanner,
    WorkspacePolicy,
)
from agent_lib.examples import FileWorkspace, make_programming_tool_runtime


ROOT = Path(__file__).resolve().parent
FIXTURE_ROOT = ROOT / "fixture"
DEFAULT_RUNS_ROOT = ROOT / "runs"


@dataclass(frozen=True)
class ProbeTask:
    task_id: str
    tier: str
    description: str
    worker_actions: list[AgentAction]
    critic_actions: list[AgentAction]
    expected_outcome: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ASC Phase 0 deterministic probe.")
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument(
        "--mode",
        choices=["worker-only", "worker-critic", "both"],
        default="both",
    )
    args = parser.parse_args(argv)

    modes = ["worker-only", "worker-critic"] if args.mode == "both" else [args.mode]
    records = []
    for mode in modes:
        for task in build_task_ladder():
            records.append(run_probe_task(task, args.runs_root, mode=mode))

    args.runs_root.mkdir(parents=True, exist_ok=True)
    output = args.runs_root / "probe_results.json"
    output.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(records, indent=2, sort_keys=True))
    print(f"wrote {output}")
    return 0


def build_task_ladder() -> list[ProbeTask]:
    return [
        ProbeTask(
            task_id="solo_extract_constant",
            tier="solo",
            description="Extract the default separator constant without changing behavior.",
            worker_actions=[
                AgentAction.tool(
                    "replace_text",
                    {
                        "path": "text_tools.py",
                        "old": "def join_labels(labels: list[str], separator: str = DEFAULT_SEPARATOR) -> str:",
                        "new": "def join_labels(labels: list[str], separator: str = DEFAULT_SEPARATOR) -> str:",
                    },
                    message="No-op refactor placeholder against an already extracted constant.",
                ),
                AgentAction.tool(
                    "run_command",
                    {"command": f"{sys.executable} -m pytest -q"},
                    message="Run characterization tests.",
                ),
                AgentAction.final("Solo refactor completed."),
            ],
            critic_actions=[],
            expected_outcome="completed_solo",
        ),
        ProbeTask(
            task_id="escalation_boundary_bug",
            tier="escalation",
            description="Worker introduces a boundary bug; critic must repair after tests fail.",
            worker_actions=[
                AgentAction.tool(
                    "replace_text",
                    {
                        "path": "text_tools.py",
                        "old": "if score <= 59:",
                        "new": "if score < 59:",
                    },
                    message="Attempt to simplify a boundary condition.",
                ),
                AgentAction.tool(
                    "run_command",
                    {"command": f"{sys.executable} -m pytest -q"},
                    message="Run characterization tests.",
                ),
            ],
            critic_actions=[
                AgentAction.tool(
                    "replace_text",
                    {
                        "path": "text_tools.py",
                        "old": "if score < 59:",
                        "new": "if score <= 59:",
                    },
                    message="Restore the pinned boundary.",
                ),
                AgentAction.tool(
                    "run_command",
                    {"command": f"{sys.executable} -m pytest -q"},
                    message="Verify critic repair.",
                ),
                AgentAction.final("Escalated repair completed."),
            ],
            expected_outcome="escalated_recovered",
        ),
    ]


def run_probe_task(task: ProbeTask, runs_root: Path, *, mode: str) -> dict[str, object]:
    workspace_root = prepare_workspace(runs_root, task.task_id, mode)
    command = f"{sys.executable} -m pytest -q"
    workspace = FileWorkspace(workspace_root)
    policy = WorkspacePolicy(
        root=str(workspace_root),
        writable_paths=["text_tools.py"],
        runnable_commands=[command],
        approval_mode="auto",
    )
    tool_runtime = make_programming_tool_runtime(workspace, policy)
    critic = (
        SequencePlanner(task.critic_actions)
        if mode == "worker-critic" and task.critic_actions
        else None
    )
    runtime = AgentRuntime(
        planner=SequencePlanner(task.worker_actions),
        critic=critic,
        tool_runtime=tool_runtime,
        engine_roles=EngineRoles(
            planner="worker", executor="worker", critic="mentor" if critic else None
        ),
    )
    run = runtime.run(
        AgentTask(task_id=task.task_id, goal=task.description, session_id=f"asc_probe_{mode}"),
        max_steps=8,
    )
    outcome = classify_outcome(run, mode=mode)
    return {
        "task_id": task.task_id,
        "tier": task.tier,
        "mode": mode,
        "expected_outcome": task.expected_outcome,
        "observed_outcome": outcome,
        "status": run.status,
        "stop_reason": run.stop_reason,
        "escalations": run.escalations,
        "steps": len(run.steps),
        "workspace": str(workspace_root),
        "tests_green": latest_test_result(run),
    }


def prepare_workspace(runs_root: Path, task_id: str, mode: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    workspace_root = runs_root / f"{timestamp}_{mode}_{task_id}"
    shutil.copytree(FIXTURE_ROOT, workspace_root)
    return workspace_root


def latest_test_result(run) -> bool | None:
    for step in reversed(run.steps):
        if step.action.tool_call is None or step.action.tool_call.name != "run_command":
            continue
        if step.observation is None or step.observation.tool_result is None:
            continue
        return bool(step.observation.tool_result.success)
    return None


def classify_outcome(run, *, mode: str) -> str:
    tests_green = latest_test_result(run)
    if run.escalations == 0 and run.status == "completed" and tests_green is True:
        return "completed_solo"
    if run.escalations > 0 and run.status == "completed" and tests_green is True:
        return "escalated_recovered"
    if run.escalations > 0 and tests_green is not True:
        return "escalated_failed"
    if mode == "worker-only" and tests_green is False:
        return "failed_without_critic"
    if run.status == "completed" and tests_green is not True:
        return "wrong_but_tests_green"
    return "failed"


if __name__ == "__main__":
    raise SystemExit(main())
