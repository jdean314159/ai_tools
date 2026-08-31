from __future__ import annotations

from dataclasses import asdict
from typing import Any

from llm_harness_core import (
    CapabilityDescriptor,
    CapabilityKind,
    MemoryRecord,
    OperationResult,
    OperationWarning,
    TraceEvent,
)

from .contracts import AgentAction, AgentRun, AgentStep, ToolCall, ToolResult


def _dict_subset(source: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source and source[key] is not None}


def _tool_execution_state(meta: dict[str, Any]) -> dict[str, Any]:
    state = _dict_subset(
        meta,
        "approval_required",
        "approval_mode",
        "patch_status",
        "policy_reason",
        "sandbox_requested_backend",
        "sandbox_backend",
        "sandbox_external",
        "sandbox_fallback_used",
        "available_sandbox_backends",
        "environment_inherited",
        "environment_keys",
        "timeout_seconds",
        "returncode",
    )
    error = meta.get("error")
    if error is not None:
        state["error"] = error
    blocked_errors = {
        "policy_violation",
        "tool_not_granted",
        "invalid_arguments",
        "invalid_path",
        "path_escape",
        "write_denied",
        "ownership_denied",
        "command_denied",
        "sandbox_unavailable",
        "invalid_sandbox_backend",
    }
    if error in blocked_errors:
        state["blocked"] = True
    if bool(meta.get("sandbox_fallback_used")):
        state["degraded"] = True
    return state


def _tool_result_warnings(result: ToolResult) -> tuple[OperationWarning, ...]:
    meta = dict(result.meta)
    state = _tool_execution_state(meta)
    warnings: list[OperationWarning] = []
    if state.get("blocked"):
        warnings.append(
            OperationWarning(
                code="tool_execution_blocked",
                message=f"Tool {result.name} was blocked by runtime policy.",
                details={"tool_name": result.name, **state},
            )
        )
    if state.get("degraded"):
        warnings.append(
            OperationWarning(
                code="tool_execution_degraded",
                message=f"Tool {result.name} used degraded execution mode.",
                details={"tool_name": result.name, **state},
            )
        )
    if meta.get("approval_required"):
        warnings.append(
            OperationWarning(
                code="tool_approval_required",
                message=f"Tool {result.name} requires approval before applying changes.",
                details={"tool_name": result.name, **state},
            )
        )
    if meta.get("error") == "command_timeout":
        warnings.append(
            OperationWarning(
                code="tool_execution_timeout",
                message=f"Tool {result.name} timed out.",
                details={"tool_name": result.name, **state},
            )
        )
    if not result.success and meta.get("error") != "command_timeout" and not state.get("blocked"):
        warnings.append(
            OperationWarning(
                code="tool_invocation_failed", message=f"Tool {result.name} failed.", details=meta
            )
        )
    return tuple(warnings)


def _run_summary(run: AgentRun) -> dict[str, Any]:
    return {
        "task_id": run.task.task_id,
        "session_id": run.task.session_id,
        "status": run.status,
        "stop_reason": run.stop_reason,
        "final_output": run.final_output,
        "step_count": len(run.steps),
        "escalations": run.escalations,
        "engine_roles": asdict(run.engine_roles),
    }


def describe_agent_runtime(runtime: Any) -> CapabilityDescriptor:
    tool_runtime = getattr(runtime, "tool_runtime", None)
    tool_specs = []
    list_tools = getattr(tool_runtime, "list_tools", None)
    if callable(list_tools):
        try:
            tool_specs = list_tools() or []
        except Exception:
            tool_specs = []
    features = [
        "agent_loop",
        "trace_events",
        "operation_results",
        "tool_execution",
        "memory_integration",
        "memory_records",
    ]
    if getattr(runtime, "critic", None) is not None:
        features.append("critic_escalation")
    if getattr(runtime, "context_builder", None) is not None:
        features.append("custom_context_builder")
    metadata = {
        "tool_count": len(tool_specs),
        "tool_names": [getattr(spec, "name", "") for spec in tool_specs],
        "max_repeated_tool_calls": getattr(runtime, "max_repeated_tool_calls", None),
        "engine_roles": asdict(getattr(runtime, "engine_roles", None))
        if getattr(runtime, "engine_roles", None) is not None
        else {},
    }
    return CapabilityDescriptor(
        kind=CapabilityKind.AGENT_RUNTIME,
        provider="agent_lib",
        component=runtime.__class__.__name__,
        version="0.1.0",
        summary="Inspectable agent runtime with planner/tool/memory composition.",
        features=tuple(features),
        input_types=("agent_task", "llm_message[]", "tool_spec[]"),
        output_types=("agent_run", "trace_event[]", "memory_record[]", "operation_result"),
        metadata=metadata,
    )


def describe_tool_runtime(tool_runtime: Any) -> CapabilityDescriptor:
    tool_specs = []
    list_tools = getattr(tool_runtime, "list_tools", None)
    if callable(list_tools):
        try:
            tool_specs = list_tools() or []
        except Exception:
            tool_specs = []
    features = ["tool_listing", "tool_invocation", "operation_results"]
    metadata = {
        "tool_count": len(tool_specs),
        "tool_names": [getattr(spec, "name", "") for spec in tool_specs],
    }
    workspace = getattr(tool_runtime, "workspace", None)
    if workspace is not None:
        features.extend(
            [
                "workspace_policy",
                "command_allowlist",
                "timeout_enforcement",
                "environment_scrubbing",
                "blocked_execution_reporting",
                "degraded_execution_reporting",
            ]
        )
        if getattr(workspace, "approval_mode", "auto") != "auto":
            features.append("approval_gates")
        if getattr(workspace, "command_isolation_backend", "host") != "host":
            features.append("external_command_isolation")
        metadata["workspace"] = (
            asdict(workspace) if hasattr(workspace, "__dataclass_fields__") else str(workspace)
        )
    return CapabilityDescriptor(
        kind=CapabilityKind.TOOL_PROVIDER,
        provider="agent_lib",
        component=tool_runtime.__class__.__name__,
        version="0.1.0",
        summary="Tool provider surfaced through agent_lib.",
        features=tuple(features),
        input_types=("tool_call",),
        output_types=("tool_result", "trace_event[]", "operation_result"),
        metadata=metadata,
    )


def action_to_dict(action: AgentAction) -> dict[str, Any]:
    payload = {
        "kind": action.kind,
        "message": action.message,
        "meta": dict(action.meta),
        "final_output": action.final_output,
    }
    if action.tool_call is not None:
        payload["tool_call"] = {
            "name": action.tool_call.name,
            "arguments": dict(action.tool_call.arguments),
        }
    return payload


def _observation_payload(step: AgentStep) -> dict[str, Any] | None:
    if step.observation is None:
        return None
    payload = {
        "kind": step.observation.kind,
        "text": step.observation.text,
        "meta": dict(step.observation.meta),
    }
    if step.observation.tool_result is not None:
        payload["tool_result"] = {
            "name": step.observation.tool_result.name,
            "output": step.observation.tool_result.output,
            "success": step.observation.tool_result.success,
            "meta": dict(step.observation.tool_result.meta),
        }
    return payload


def _step_memory_records(step: AgentStep) -> list[MemoryRecord]:
    records: list[MemoryRecord] = []
    base_meta = {
        "step_index": step.index,
        "action_kind": step.action.kind,
        "engine_role": step.action.meta.get("engine_role"),
    }
    if step.action.message:
        records.append(
            MemoryRecord(
                text=step.action.message,
                source="agent_lib.action",
                record_id=f"step-{step.index}-action",
                metadata={**base_meta, "message_role": "agent_action"},
            )
        )
    if step.action.final_output:
        records.append(
            MemoryRecord(
                text=step.action.final_output,
                source="agent_lib.final_output",
                record_id=f"step-{step.index}-final",
                metadata={**base_meta, "message_role": "final_output"},
            )
        )
    if step.observation is not None and step.observation.text:
        obs_meta = {
            **base_meta,
            "observation_kind": step.observation.kind,
            **dict(step.observation.meta),
        }
        if step.observation.tool_result is not None:
            obs_meta.update(
                {
                    "tool_name": step.observation.tool_result.name,
                    "tool_success": step.observation.tool_result.success,
                }
            )
        records.append(
            MemoryRecord(
                text=step.observation.text,
                source="agent_lib.observation",
                record_id=f"step-{step.index}-observation",
                metadata=obs_meta,
            )
        )
    return records


def run_to_memory_records(run: AgentRun) -> tuple[MemoryRecord, ...]:
    records: list[MemoryRecord] = [
        MemoryRecord(
            text=run.task.goal,
            source="agent_lib.task",
            record_id=run.task.task_id,
            metadata={
                "task_id": run.task.task_id,
                "session_id": run.task.session_id,
                "kind": "agent_task",
            },
        )
    ]
    for step in run.steps:
        records.extend(_step_memory_records(step))
    if run.final_output and (not records or records[-1].text != run.final_output):
        records.append(
            MemoryRecord(
                text=run.final_output,
                source="agent_lib.run_summary",
                record_id=f"{run.task.task_id}-final",
                metadata={
                    "task_id": run.task.task_id,
                    "session_id": run.task.session_id,
                    "status": run.status,
                    "stop_reason": run.stop_reason,
                    "kind": "agent_run_final_output",
                },
            )
        )
    return tuple(records)


def _run_warnings(run: AgentRun) -> tuple[OperationWarning, ...]:
    warnings: list[OperationWarning] = []
    if run.status != "completed":
        warnings.append(
            OperationWarning(
                code="agent_run_not_completed",
                message=f"Agent run ended with status={run.status}.",
                details={"stop_reason": run.stop_reason, "task_id": run.task.task_id},
            )
        )
    for step in run.steps:
        tool_result = step.observation.tool_result if step.observation is not None else None
        if tool_result is not None and not tool_result.success:
            warnings.append(
                OperationWarning(
                    code="agent_tool_failure",
                    message=f"Tool {tool_result.name} failed during agent run.",
                    details={
                        "task_id": run.task.task_id,
                        "step_index": step.index,
                        "tool_name": tool_result.name,
                        **dict(tool_result.meta),
                    },
                )
            )
    return tuple(warnings)


def step_to_interop_events(step: AgentStep) -> list[TraceEvent]:
    if step.trace is not None:
        return list(step.trace.to_interop_events())
    payload: dict[str, Any] = {"step_index": step.index, "action": action_to_dict(step.action)}
    observation = _observation_payload(step)
    if observation is not None:
        payload["observation"] = observation
    return [
        TraceEvent(
            event_type="agent_step_recorded",
            source_package="agent_lib",
            source_component="interop",
            payload=payload,
            severity="info",
            message=f"Captured agent step {step.index}.",
            tags=("agent", "step"),
        )
    ]


def run_to_interop_events(run: AgentRun) -> list[TraceEvent]:
    events = [
        TraceEvent(
            event_type="agent_run_started",
            source_package="agent_lib",
            source_component="interop",
            payload={
                "task_id": run.task.task_id,
                "session_id": run.task.session_id,
                "goal": run.task.goal,
                "engine_roles": asdict(run.engine_roles),
            },
            severity="info",
            message="Agent run started.",
            tags=("agent", "run"),
            ts=run.started_at.timestamp() if run.started_at is not None else None,
        )
    ]
    for step in run.steps:
        events.extend(step_to_interop_events(step))
    final_severity = "info" if run.status == "completed" else "warning"
    events.append(
        TraceEvent(
            event_type="agent_run_finished",
            source_package="agent_lib",
            source_component="interop",
            payload=_run_summary(run),
            severity=final_severity,
            message=f"Agent run finished with status={run.status}.",
            tags=("agent", "run", "completed" if run.status == "completed" else "stopped"),
            ts=run.finished_at.timestamp() if run.finished_at is not None else None,
        )
    )
    return events


def tool_result_to_operation_result(
    result: ToolResult, *, call: ToolCall | None = None
) -> OperationResult[dict[str, Any]]:
    meta = dict(result.meta)
    execution_state = _tool_execution_state(meta)
    diagnostics = {
        "trace_events": (
            TraceEvent(
                event_type="agent_tool_result",
                source_package="agent_lib",
                source_component="LocalToolRuntime",
                payload={
                    "call": None
                    if call is None
                    else {"name": call.name, "arguments": dict(call.arguments)},
                    "name": result.name,
                    "success": result.success,
                    "meta": meta,
                    "execution_state": execution_state,
                },
                severity="info"
                if result.success and not execution_state.get("degraded")
                else "warning",
                message=f"Tool {result.name} completed."
                if result.success
                else f"Tool {result.name} failed.",
                tags=("agent", "tool", "observation"),
            ),
        ),
        "capability": None,
        "execution_state": execution_state,
    }
    value = {
        "name": result.name,
        "output": result.output,
        "success": result.success,
        "meta": meta,
        "execution_state": execution_state,
    }
    return OperationResult.success(
        value, warnings=_tool_result_warnings(result), diagnostics=diagnostics
    )


def run_to_operation_result(
    run: AgentRun, *, runtime: Any | None = None
) -> OperationResult[dict[str, Any]]:
    events = run_to_interop_events(run)
    records = run_to_memory_records(run)
    warnings_list = list(_run_warnings(run))
    blocked_actions: list[dict[str, Any]] = []
    degraded_actions: list[dict[str, Any]] = []
    approval_actions: list[dict[str, Any]] = []
    execution_modes: list[dict[str, Any]] = []
    for step in run.steps:
        tool_result = step.observation.tool_result if step.observation is not None else None
        if tool_result is None:
            continue
        state = _tool_execution_state(dict(tool_result.meta))
        if state:
            execution_modes.append(
                {"step_index": step.index, "tool_name": tool_result.name, **state}
            )
        if state.get("blocked"):
            blocked_actions.append(
                {"step_index": step.index, "tool_name": tool_result.name, **state}
            )
        if state.get("degraded"):
            degraded_actions.append(
                {"step_index": step.index, "tool_name": tool_result.name, **state}
            )
        if state.get("approval_required"):
            approval_actions.append(
                {"step_index": step.index, "tool_name": tool_result.name, **state}
            )
        warnings_list.extend(_tool_result_warnings(tool_result))
    warnings = tuple(warnings_list)
    value = {
        "summary": _run_summary(run),
        "steps": [
            {
                "index": step.index,
                "action": action_to_dict(step.action),
                "observation": _observation_payload(step),
                "events": [
                    {
                        "event_type": event.event_type,
                        "source_package": event.source_package,
                        "source_component": event.source_component,
                        "payload": dict(event.payload),
                        "severity": event.severity,
                        "message": event.message,
                        "tags": list(event.tags),
                    }
                    for event in step_to_interop_events(step)
                ],
            }
            for step in run.steps
        ],
    }
    diagnostics = dict(run.meta)
    diagnostics.update(
        {
            "started_at": run.started_at.isoformat() if run.started_at is not None else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at is not None else None,
            "elapsed_seconds": run.elapsed_seconds,
            "event_count": len(events),
            "trace_events": events,
            "memory_records": records,
            "capability": describe_agent_runtime(runtime) if runtime is not None else None,
            "blocked_actions": blocked_actions,
            "degraded_actions": degraded_actions,
            "approval_actions": approval_actions,
            "execution_modes": execution_modes,
        }
    )
    return OperationResult.success(value, warnings=warnings, diagnostics=diagnostics)
