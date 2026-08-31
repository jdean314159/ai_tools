"""Frozen deterministic probe for agent policy and observability completeness."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from agent_lib import (
    AgentAction,
    AgentRuntime,
    AgentTask,
    LocalTool,
    LocalToolRuntime,
    SequencePlanner,
    ToolResult,
    WorkspacePolicy,
    run_to_operation_result,
)
from agent_lib.programming import ProgrammingToolRuntime
from llm_harness_core import prepare_new_artifact_path


PROFILE = "examples.agent_policy_observability"
PROFILE_VERSION = 2


@dataclass(frozen=True)
class PolicyCase:
    case_id: str
    tool_name: str
    arguments: dict[str, Any]
    expected_error: str | None
    expected_signal: str


def cases() -> tuple[PolicyCase, ...]:
    return (
        PolicyCase(
            "tool_not_granted", "replace_text", {"path": "main.py"}, "tool_not_granted", "blocked"
        ),
        PolicyCase(
            "path_escape", "read_file", {"path": "../outside.txt"}, "path_escape", "blocked"
        ),
        PolicyCase(
            "write_denied", "replace_text", {"path": "denied.py"}, "write_denied", "blocked"
        ),
        PolicyCase(
            "command_denied", "run_command", {"command": "echo denied"}, "command_denied", "blocked"
        ),
        PolicyCase("approval_required", "replace_text", {"path": "main.py"}, None, "approval"),
        PolicyCase("objective_failure", "check", {}, "verification_mismatch", "escalation"),
    )


def suite_digest() -> str:
    raw = json.dumps([asdict(case) for case in cases()], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _policy_for(case: PolicyCase, root: Path) -> WorkspacePolicy:
    common = {"root": str(root), "enforce_patch_ownership": False}
    if case.case_id == "tool_not_granted":
        return WorkspacePolicy(allowed_tools=["read_file"], writable_paths=["main.py"], **common)
    if case.case_id == "path_escape":
        return WorkspacePolicy(allowed_tools=["read_file"], **common)
    if case.case_id == "write_denied":
        return WorkspacePolicy(
            allowed_tools=["replace_text"], writable_paths=["allowed.py"], **common
        )
    if case.case_id == "command_denied":
        return WorkspacePolicy(allowed_tools=["run_command"], runnable_commands=[], **common)
    if case.case_id == "approval_required":
        return WorkspacePolicy(
            allowed_tools=["replace_text"],
            writable_paths=["main.py"],
            approval_mode="human_checkpoint",
            **common,
        )
    return WorkspacePolicy(allowed_tools=["check"], **common)


def _inner_runtime() -> LocalToolRuntime:
    def unexpected(**kwargs: Any) -> ToolResult:
        del kwargs
        return ToolResult(name="unexpected", output="handler unexpectedly executed", success=False)

    return LocalToolRuntime(
        [
            LocalTool("read_file", "Synthetic read target.", unexpected),
            LocalTool("replace_text", "Synthetic write target.", unexpected),
            LocalTool("run_command", "Synthetic command target.", unexpected),
            LocalTool(
                "check",
                "Deterministic objective verifier.",
                lambda: ToolResult(
                    name="check",
                    output="synthetic mismatch",
                    success=False,
                    meta={"error": "verification_mismatch"},
                ),
            ),
        ]
    )


def _event_types(step: Any) -> set[str]:
    return (
        {event.event_type for event in step.trace.to_interop_events()}
        if step.trace is not None
        else set()
    )


def _run_case(case: PolicyCase, *, root: Path) -> dict[str, Any]:
    policy = _policy_for(case, root)
    planner = SequencePlanner(
        [
            AgentAction.tool(
                case.tool_name, case.arguments, message="Exercise the frozen policy boundary."
            ),
            AgentAction.final("Worker completed after the observed tool result."),
        ]
    )
    critic = None
    if case.expected_signal == "escalation":
        critic = SequencePlanner(
            [
                AgentAction.final(
                    "Critic acknowledged the objective failure.", meta={"engine_role": "critic"}
                ),
            ]
        )
    tools = ProgrammingToolRuntime(_inner_runtime(), policy, root=root)
    runtime = AgentRuntime(planner=planner, critic=critic, tool_runtime=tools)
    task = AgentTask(
        task_id=case.case_id,
        goal="Characterize one deterministic policy boundary.",
        context={"workspace_policy": asdict(policy)},
    )
    run = runtime.run(task, max_steps=3)
    result = run_to_operation_result(run, runtime=runtime)
    first = run.steps[0]
    tool_result = first.observation.tool_result if first.observation is not None else None
    first_events = _event_types(first)
    trace_tags = {
        tag
        for event in (first.trace.events if first.trace is not None else [])
        for tag in event.tags
    }
    warning_codes = {warning.code for warning in result.warnings}
    blocked_interop = len(result.diagnostics["blocked_actions"]) == 1
    blocked_trace = "blocked" in trace_tags
    approval_interop = len(result.diagnostics["approval_actions"]) == 1
    approval_trace = "approval" in trace_tags
    escalation_summary = run.escalations == 1 and run.stop_reason == "critic_completed"
    escalation_trace = any(
        step.trace is not None
        and any(
            event.event_type == "agent_action_selected"
            and event.payload.get("controller") == "critic"
            and event.payload.get("escalated") is True
            for event in step.trace.events
        )
        for step in run.steps
    )
    common_trace_complete = {
        "agent_action_selected",
        "agent_workspace_policy",
        "agent_tool_invoked",
        "agent_tool_result",
    }.issubset(first_events)

    if case.expected_signal == "blocked":
        signal_complete = (
            blocked_interop and blocked_trace and "tool_execution_blocked" in warning_codes
        )
    elif case.expected_signal == "approval":
        signal_complete = (
            approval_interop and approval_trace and "tool_approval_required" in warning_codes
        )
    else:
        signal_complete = (
            escalation_summary and escalation_trace and "agent_tool_failure" in warning_codes
        )
    return {
        "case_id": case.case_id,
        "expected_signal": case.expected_signal,
        "expected_error": case.expected_error,
        "observed_error": None if tool_result is None else tool_result.meta.get("error"),
        "tool_success": None if tool_result is None else tool_result.success,
        "common_trace_complete": common_trace_complete,
        "blocked_interop": blocked_interop,
        "blocked_trace": blocked_trace,
        "approval_interop": approval_interop,
        "approval_trace": approval_trace,
        "escalation_summary": escalation_summary,
        "escalation_trace": escalation_trace,
        "warning_codes": sorted(warning_codes),
        "signal_complete": signal_complete,
    }


def run_experiment(*, workspace_root: Path) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    observations = [_run_case(case, root=workspace_root / case.case_id) for case in cases()]
    errors_match = all(item["observed_error"] == item["expected_error"] for item in observations)
    common_traces_complete = all(item["common_trace_complete"] for item in observations)
    signals_complete = all(item["signal_complete"] for item in observations)
    return {
        "schema_version": 1,
        "profile": PROFILE,
        "profile_version": PROFILE_VERSION,
        "suite_digest": suite_digest(),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model_used": False,
        "case_count": len(observations),
        "acceptance_gate": {
            "require_expected_policy_outcomes": True,
            "require_common_trace_events": True,
            "require_signal_parity": True,
            "expected_policy_outcomes": errors_match,
            "common_trace_events": common_traces_complete,
            "signal_parity": signals_complete,
            "passed": errors_match and common_traces_complete and signals_complete,
        },
        "observations": observations,
        "privacy": {
            "raw_tool_outputs_retained": False,
            "workspace_paths_retained": False,
            "environment_retained": False,
        },
        "interpretation_limit": (
            "Six deterministic native-runtime cases; tests policy and shared-observability parity, "
            "not OS/container isolation or model planning quality."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args(argv)
    target = prepare_new_artifact_path(args.artifact)
    with tempfile.TemporaryDirectory(prefix="agent-policy-observability-") as tmp:
        body = run_experiment(workspace_root=Path(tmp))
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in body.items() if key != "observations"},
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if body["acceptance_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
