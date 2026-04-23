from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import time
from typing import Any, Sequence

from llm_inspector import ContextResult, RunMetrics, Section, TokenAccounting, Trace, TraceEvent, Turn

from .contracts import (
    AgentAction,
    AgentContext,
    AgentMemoryAdapter,
    AgentObservation,
    AgentRun,
    AgentStep,
    AgentTask,
    AgentTraceEmitter,
    EngineRoles,
    Planner,
    ToolRuntime,
    AgentRunLifecycleHook,
    AgentContextBuilder,
)
from .memory import NullMemoryAdapter


def _workspace_summary(task: AgentTask) -> dict[str, Any]:
    context = task.context if isinstance(task.context, dict) else {}
    workspace = context.get("workspace_policy")
    if not isinstance(workspace, dict):
        return {}
    return {
        "root": workspace.get("root"),
        "approval_mode": workspace.get("approval_mode"),
        "isolation_mode": workspace.get("isolation_mode"),
        "enforce_patch_ownership": bool(workspace.get("enforce_patch_ownership", False)),
        "writable_paths": list(workspace.get("writable_paths") or []),
        "runnable_commands": list(workspace.get("runnable_commands") or []),
        "command_timeout_seconds": workspace.get("command_timeout_seconds"),
        "max_command_output_chars": workspace.get("max_command_output_chars"),
        "inherit_environment": bool(workspace.get("inherit_environment", False)),
        "allowed_environment_keys": list(workspace.get("allowed_environment_keys") or []),
        "denied_environment_keys": list(workspace.get("denied_environment_keys") or []),
        "command_isolation_backend": workspace.get("command_isolation_backend"),
        "command_isolation_image": workspace.get("command_isolation_image"),
        "command_isolation_network": bool(workspace.get("command_isolation_network", False)),
        "command_isolation_fallback_to_host": bool(workspace.get("command_isolation_fallback_to_host", False)),
    }


def _agent_summary(context: AgentContext, observation: AgentObservation | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "active_controller": context.active_controller,
        "escalated": context.escalated,
        "step_count": len(context.steps),
        "tool_count": len(context.tool_specs),
        "tool_names": [spec.name for spec in context.tool_specs],
        "engine_roles": asdict(context.engine_roles),
    }
    workspace = _workspace_summary(context.task)
    if workspace:
        summary["workspace_policy"] = workspace
    if context.memory_trace is not None:
        summary["memory_backend"] = context.memory_trace.metrics.engine
        summary["memory_evidence_count"] = len(context.memory_trace.context.evidence)
    return _merge_execution_observation(summary, observation)




def _merge_execution_observation(summary: dict[str, Any], observation: AgentObservation | None) -> dict[str, Any]:
    merged = dict(summary)
    merged.setdefault("blocked_count", 0)
    merged.setdefault("degraded_count", 0)
    merged.setdefault("approval_count", 0)
    modes = list(merged.get("execution_modes") or [])
    if observation is None or observation.tool_result is None:
        merged["execution_modes"] = modes
        return merged
    meta = dict(observation.tool_result.meta)
    mode = {
        "tool_name": observation.tool_result.name,
        "approval_required": bool(meta.get("approval_required", False)),
        "sandbox_requested_backend": meta.get("sandbox_requested_backend"),
        "sandbox_backend": meta.get("sandbox_backend"),
        "sandbox_external": bool(meta.get("sandbox_external", False)),
        "sandbox_fallback_used": bool(meta.get("sandbox_fallback_used", False)),
        "policy_reason": meta.get("policy_reason"),
        "returncode": meta.get("returncode"),
    }
    blocked_errors = {"policy_violation", "invalid_arguments", "invalid_path", "path_escape", "write_denied", "ownership_denied", "command_denied", "sandbox_unavailable", "invalid_sandbox_backend"}
    blocked = str(meta.get("error") or "") in blocked_errors
    degraded = bool(meta.get("sandbox_fallback_used"))
    approval = bool(meta.get("approval_required"))
    mode["blocked"] = blocked
    mode["degraded"] = degraded
    modes.append(mode)
    if blocked:
        merged["blocked_count"] = int(merged.get("blocked_count", 0)) + 1
    if degraded:
        merged["degraded_count"] = int(merged.get("degraded_count", 0)) + 1
    if approval:
        merged["approval_count"] = int(merged.get("approval_count", 0)) + 1
    merged["execution_modes"] = modes
    return merged

def _observation_payload(observation: AgentObservation) -> dict[str, Any]:
    payload = {
        "kind": observation.kind,
        "text": observation.text,
        "meta": dict(observation.meta),
    }
    if observation.tool_result is not None:
        payload["tool_result"] = {
            "name": observation.tool_result.name,
            "success": observation.tool_result.success,
            "output": observation.tool_result.output,
            "meta": dict(observation.tool_result.meta),
        }
    return payload


class InspectorTraceEmitter:
    def emit_step(
        self,
        *,
        context: AgentContext,
        action: AgentAction,
        observation: AgentObservation | None,
    ) -> Trace:
        sections = [
            Section(title="Task", text=context.task.goal, origin="user"),
        ]
        if context.recalled:
            sections.append(
                Section(
                    title="Memory",
                    text="\n".join(item.text for item in context.recalled),
                    origin="working",
                )
            )
        if context.tool_specs:
            sections.append(
                Section(
                    title="Tools",
                    text=", ".join(spec.name for spec in context.tool_specs),
                    origin="system",
                )
            )
        context_budget = context.task.context.get("context_budget") if isinstance(context.task.context, dict) else None
        if isinstance(context_budget, dict):
            compacted = int(context_budget.get("compacted_step_count") or 0)
            visible = int(context_budget.get("visible_step_count") or len(context.steps))
            refs = len(list(context_budget.get("artifacts") or []))
            sections.append(
                Section(
                    title="Context Budget",
                    text=f"visible_steps={visible}; compacted_steps={compacted}; output_refs={refs}",
                    origin="system",
                )
            )
        programming_state = context.task.context.get("programming_state") if isinstance(context.task.context, dict) else None
        if isinstance(programming_state, dict):
            current_step = str(programming_state.get("current_step_id") or "(none)")
            status = str(programming_state.get("status") or "running")
            step_count = int(programming_state.get("step_count") or 0)
            sections.append(
                Section(
                    title="Programming State",
                    text=f"status={status}; current_step={current_step}; step_count={step_count}",
                    origin="system",
                )
            )

        engine_role = str(action.meta.get("engine_role") or context.active_controller)
        model = str(
            action.meta.get("model_name")
            or {
                "planner": context.engine_roles.planner,
                "executor": context.engine_roles.executor,
                "critic": context.engine_roles.critic,
                "fallback": context.engine_roles.fallback,
            }.get(engine_role)
            or engine_role
        )
        active_optimizations = action.meta.get("active_optimizations")
        if not isinstance(active_optimizations, list):
            active_optimizations = []

        events = [
            TraceEvent(
                event_type="agent_action_selected",
                source_package="agent_lib",
                source_component="InspectorTraceEmitter",
                payload={
                    "action": asdict(action),
                    "controller": context.active_controller,
                    "engine_role": engine_role,
                    "escalated": context.escalated,
                },
                severity="info",
                message=f"{context.active_controller} produced {action.kind}",
                tags=("agent", "planning"),
            ),
        ]
        workspace = _workspace_summary(context.task)
        if workspace:
            events.append(
                TraceEvent(
                    event_type="agent_workspace_policy",
                    source_package="agent_lib",
                    source_component="InspectorTraceEmitter",
                    payload=workspace,
                    severity="info",
                    message="Attached workspace policy and execution boundaries.",
                    tags=("agent", "safety", "workspace"),
                )
            )
        if context.memory_trace is not None:
            events.append(
                TraceEvent(
                    event_type="agent_memory_recall_attached",
                    source_package="agent_lib",
                    source_component="InspectorTraceEmitter",
                    payload={
                        "memory_backend": context.memory_trace.metrics.engine,
                        "evidence_count": len(context.memory_trace.context.evidence),
                    },
                    severity="info",
                    message="Attached memory recall trace.",
                    tags=("agent", "memory"),
                )
            )
        if action.kind == "tool" and action.tool_call is not None:
            events.append(
                TraceEvent(
                    event_type="agent_tool_invoked",
                    source_package="agent_lib",
                    source_component="InspectorTraceEmitter",
                    payload={
                        "name": action.tool_call.name,
                        "arguments": dict(action.tool_call.arguments),
                        "controller": context.active_controller,
                        "engine_role": engine_role,
                    },
                    severity="info",
                    message=f"Invoking tool {action.tool_call.name}.",
                    tags=("agent", "tool"),
                )
            )
        if observation is not None:
            severity = "info"
            tags = ["agent", "observation"]
            event_type = "agent_observation"
            if observation.tool_result is not None:
                event_type = "agent_tool_result"
                tags = ["agent", "tool", "observation"]
                if not observation.tool_result.success:
                    severity = "warning"
                    tags.append("failure")
                if observation.tool_result.meta.get("approval_required"):
                    tags.append("approval")
                if observation.tool_result.meta.get("policy_reason"):
                    tags.append("policy")
                if observation.tool_result.meta.get("sandbox_fallback_used"):
                    tags.append("degraded")
                blocked_errors = {"policy_violation", "invalid_arguments", "invalid_path", "path_escape", "write_denied", "ownership_denied", "command_denied", "sandbox_unavailable", "invalid_sandbox_backend"}
                if str(observation.tool_result.meta.get("error") or "") in blocked_errors:
                    severity = "warning"
                    tags.append("blocked")
            events.append(
                TraceEvent(
                    event_type=event_type,
                    source_package="agent_lib",
                    source_component="InspectorTraceEmitter",
                    payload=_observation_payload(observation),
                    severity=severity,
                    message=observation.kind,
                    tags=tuple(tags),
                )
            )

        return Trace(
            turn=Turn(role="user", text=context.task.goal, session_id=context.task.session_id),
            context=ContextResult(
                sections=sections,
                evidence=list(context.recalled),
                token_accounting=TokenAccounting(
                    total_tokens=sum(max(1, len(section.text.split())) for section in sections),
                ),
                signals={
                    "step_count": len(context.steps),
                    "controller": context.active_controller,
                    "escalated": context.escalated,
                    "agent_summary": _agent_summary(context, observation),
                },
            ),
            metrics=RunMetrics(
                engine=engine_role,
                model=model,
                inference_optimizations=[dict(item) for item in active_optimizations if isinstance(item, dict)],
            ),
            events=events,
        )


class AgentRuntime:
    def __init__(
        self,
        *,
        planner: Planner,
        tool_runtime: ToolRuntime,
        memory: AgentMemoryAdapter | None = None,
        trace_emitter: AgentTraceEmitter | None = None,
        engine_roles: EngineRoles | None = None,
        critic: Planner | None = None,
        lifecycle_hooks: Sequence[AgentRunLifecycleHook] | None = None,
        max_repeated_tool_calls: int = 3,
        context_builder: AgentContextBuilder | None = None,
    ) -> None:
        self.planner = planner
        self.tool_runtime = tool_runtime
        self.memory = memory or NullMemoryAdapter()
        self.trace_emitter = trace_emitter or InspectorTraceEmitter()
        self.engine_roles = engine_roles or EngineRoles()
        self.critic = critic
        self.lifecycle_hooks = list(lifecycle_hooks or [])
        self.max_repeated_tool_calls = max(1, int(max_repeated_tool_calls))
        self.context_builder = context_builder

    def describe_component(self):
        from .interop import describe_agent_runtime
        return describe_agent_runtime(self)

    def get_capability_descriptor(self):
        from .interop import describe_agent_runtime
        return describe_agent_runtime(self)

    def run_interop(self, task: AgentTask, *, max_steps: int = 8):
        from .interop import run_to_operation_result
        run = self.run(task, max_steps=max_steps)
        return run_to_operation_result(run, runtime=self)

    def _build_context(self, task: AgentTask, steps: Sequence[AgentStep], *, active_controller: str, escalated: bool) -> AgentContext:
        tool_specs = self.tool_runtime.list_tools()
        if self.context_builder is not None:
            return self.context_builder.build_context(
                task,
                steps,
                active_controller=active_controller,
                escalated=escalated,
                memory=self.memory,
                tool_specs=tool_specs,
                engine_roles=self.engine_roles,
            )
        recalled = self.memory.recall(task, steps, limit=5)
        trace_recall = getattr(self.memory, "trace_recall", None)
        memory_trace = trace_recall(task, steps, limit=5) if callable(trace_recall) else None
        return AgentContext(
            task=task,
            steps=list(steps),
            recalled=recalled,
            memory_trace=memory_trace,
            tool_specs=tool_specs,
            engine_roles=self.engine_roles,
            active_controller=active_controller,
            escalated=escalated,
        )

    def _should_escalate(self, run: AgentRun) -> bool:
        if self.critic is None or not run.steps:
            return False
        last = run.steps[-1]
        if last.observation and last.observation.tool_result is not None and not last.observation.tool_result.success:
            return True
        if bool(last.action.meta.get("needs_critic")):
            return True
        if last.observation and bool(last.observation.meta.get("needs_critic")):
            return True
        return False

    def _should_stop_for_repeat(self, run: AgentRun, action: AgentAction) -> bool:
        if action.kind != "tool" or action.tool_call is None:
            return False
        recent = []
        for step in reversed(run.steps):
            if step.action.kind != "tool" or step.action.tool_call is None:
                break
            recent.append(step.action.tool_call)
            if len(recent) >= self.max_repeated_tool_calls - 1:
                break
        if len(recent) < self.max_repeated_tool_calls - 1:
            return False
        return all(call == action.tool_call for call in recent)

    def _finalize_run(self, run: AgentRun, started_clock: float) -> AgentRun:
        if run.finished_at is None:
            run.finished_at = datetime.now(timezone.utc)
        if run.elapsed_seconds is None:
            run.elapsed_seconds = max(0.0, time.perf_counter() - started_clock)
        run.meta.setdefault("elapsed_seconds", run.elapsed_seconds)
        if run.started_at is not None:
            run.meta.setdefault("started_at", run.started_at.isoformat())
        if run.finished_at is not None:
            run.meta.setdefault("finished_at", run.finished_at.isoformat())
        return run

    def run(self, task: AgentTask, *, max_steps: int = 8) -> AgentRun:
        started_at = datetime.now(timezone.utc)
        started_clock = time.perf_counter()
        run = AgentRun(task=task, engine_roles=self.engine_roles, started_at=started_at)
        active_controller = str(task.context.get("resume_controller") or "planner").strip().lower() or "planner"

        for hook in self.lifecycle_hooks:
            hook.on_start(task, max_steps=max_steps, engine_roles=self.engine_roles)

        for index in range(1, max_steps + 1):
            should_escalate = self._should_escalate(run)
            if should_escalate:
                active_controller = "critic"
                run.escalations += 1
            elif active_controller == "critic" and self.critic is not None and run.steps:
                last = run.steps[-1]
                if str(last.action.meta.get("handoff", "")).strip().lower() == "planner":
                    active_controller = str(task.context.get("resume_controller") or "planner").strip().lower() or "planner"

            context = self._build_context(task, run.steps, active_controller=active_controller, escalated=active_controller == "critic")
            retry_payload = task.context.pop("_programming_retry_action", None)
            if isinstance(retry_payload, dict) and retry_payload.get("name"):
                action = AgentAction.tool(
                    str(retry_payload.get("name")),
                    dict(retry_payload.get("arguments") or {}),
                    message=str(retry_payload.get("message") or "Retry the previous tool call."),
                    meta=dict(retry_payload.get("meta") or {}),
                )
            else:
                active_planner = self.critic if active_controller == "critic" and self.critic is not None else self.planner
                action = active_planner.plan(context)
            if self._should_stop_for_repeat(run, action):
                run.status = "stopped"
                run.stop_reason = "planner_stop"
                run.final_output = f"Interrupted repeated tool call: {action.tool_call.name}" if action.tool_call is not None else "Interrupted repeated tool call."
                for hook in self.lifecycle_hooks:
                    hook.on_finish(run)
                return self._finalize_run(run, started_clock)
            action_meta = dict(action.meta)
            action_meta.setdefault("engine_role", active_controller if active_controller != "planner" else ("executor" if action.kind == "tool" else "planner"))
            action = AgentAction(
                kind=action.kind,
                message=action.message,
                tool_call=action.tool_call,
                final_output=action.final_output,
                meta=action_meta,
            )

            observation: AgentObservation | None = None
            if action.kind == "tool":
                if action.tool_call is None:
                    raise ValueError("Tool actions must provide tool_call")
                result = self.tool_runtime.invoke(action.tool_call)
                observation = AgentObservation(
                    kind="tool_result",
                    text=str(result.output),
                    tool_result=result,
                    meta=dict(result.meta),
                )
            elif action.kind == "message":
                observation = AgentObservation(kind="message", text=action.message, meta=dict(action.meta))

            trace = self.trace_emitter.emit_step(context=context, action=action, observation=observation)
            step = AgentStep(index=index, action=action, observation=observation, trace=trace)
            run.steps.append(step)
            self.memory.record_step(task, step)
            for hook in self.lifecycle_hooks:
                hook.on_step(task, context, step, run)

            stop_payload = task.context.pop("_programming_stop", None)
            if isinstance(stop_payload, dict):
                run.status = "stopped"
                run.stop_reason = str(stop_payload.get("reason") or "planner_stop")
                run.final_output = str(stop_payload.get("final_output") or "Stopped by policy.")
                for hook in self.lifecycle_hooks:
                    hook.on_finish(run)
                return self._finalize_run(run, started_clock)

            next_controller = str(task.context.pop("_programming_next_controller", "") or "").strip().lower()
            if next_controller in {"planner", "critic"}:
                active_controller = next_controller
                task.context["resume_controller"] = next_controller
            elif task.context.get("resume_controller"):
                task.context.pop("resume_controller", None)

            if action.kind == "final":
                run.status = "completed"
                run.stop_reason = "critic_completed" if active_controller == "critic" else "completed"
                run.final_output = action.final_output or action.message
                for hook in self.lifecycle_hooks:
                    hook.on_finish(run)
                return self._finalize_run(run, started_clock)

        run.status = "stopped"
        run.stop_reason = "max_steps"
        if run.steps and run.steps[-1].observation is not None:
            run.final_output = run.steps[-1].observation.text
        for hook in self.lifecycle_hooks:
            hook.on_finish(run)
        return run
