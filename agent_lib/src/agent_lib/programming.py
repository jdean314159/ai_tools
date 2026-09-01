from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
import shlex
import signal
import subprocess
from typing import Any, Sequence

from .programming_contracts import (
    FailurePolicy,
    PatchProposal as _PatchProposal,
    PlanStatus as _PlanStatus,
    PlanStep,
    ProgrammingTask,
    ToolFailurePolicy,
    VerificationResult as _VerificationResult,
)
from .programming_state import (
    ProgrammingStateTracker,
    ProgrammingTaskState as _ProgrammingTaskState,
    ProgrammingTaskStateStore as _ProgrammingTaskStateStore,
)
from .programming_workspace import (
    ApprovalMode,
    CommandExecutionResult,
    IsolationMode as _IsolationMode,
    PatchOwnership as _PatchOwnership,
    SandboxBackend as _SandboxBackend,
    WorkspaceAllocation as _WorkspaceAllocation,
    WorkspaceIsolationManager,
    WorkspacePolicy,
    _build_command_environment,
    _build_container_command,
    _command_allowed,
    _normalize_rel_path as _workspace_normalize_rel_path,
    _path_matches_allowlist,
    _resolve_command_isolation_backend,
    _truncate_output,
)

from .contracts import (
    AgentContext,
    AgentObservation,
    AgentRun,
    AgentRunLifecycleHook,
    AgentStep,
    AgentTask,
    EngineRoles,
    ToolCall,
    ToolResult,
    ToolSpec,
    ToolRuntime,
)

IsolationMode = _IsolationMode
PatchOwnership = _PatchOwnership
SandboxBackend = _SandboxBackend
WorkspaceAllocation = _WorkspaceAllocation
_normalize_rel_path = _workspace_normalize_rel_path
PatchProposal = _PatchProposal
PlanStatus = _PlanStatus
VerificationResult = _VerificationResult
ProgrammingTaskState = _ProgrammingTaskState
ProgrammingTaskStateStore = _ProgrammingTaskStateStore

RELEASE_PATCH_LEASE_TOOL = "release_patch_lease"


class ProgrammingToolRuntime:
    def __init__(
        self,
        inner: ToolRuntime,
        workspace: WorkspacePolicy,
        *,
        root: str | Path,
        owner_id: str = "worker",
        isolation_manager: WorkspaceIsolationManager | None = None,
    ) -> None:
        self.inner = inner
        self.workspace = workspace
        self.root = Path(root).expanduser().resolve()
        self.owner_id = str(owner_id or "worker").strip() or "worker"
        self.isolation_manager = isolation_manager

    def describe_component(self):
        from .interop import describe_tool_runtime

        return describe_tool_runtime(self)

    def get_capability_descriptor(self):
        from .interop import describe_tool_runtime

        return describe_tool_runtime(self)

    def list_tools(self) -> list[ToolSpec]:
        tools = self.inner.list_tools()
        if self.isolation_manager is not None and (
            self.workspace.allowed_tools is None
            or RELEASE_PATCH_LEASE_TOOL in self.workspace.allowed_tools
        ):
            tools.append(
                ToolSpec(
                    name=RELEASE_PATCH_LEASE_TOOL,
                    description="Release this worker's active patch lease for a workspace-relative path.",
                    input_schema={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                )
            )
        return tools

    def _deny(self, call: ToolCall, *, reason: str, error: str = "policy_violation") -> ToolResult:
        return ToolResult(
            name=call.name,
            output=reason,
            success=False,
            meta={"error": error, "policy_reason": reason},
        )

    def _proposal_result(
        self, call: ToolCall, *, message: str, approval_mode: ApprovalMode
    ) -> ToolResult:
        return ToolResult(
            name=call.name,
            output=message,
            success=True,
            meta={
                "approval_required": True,
                "approval_mode": approval_mode,
                "patch_status": "proposed",
                "patch_proposal": dict(call.arguments),
            },
        )

    def invoke(self, call: ToolCall) -> ToolResult:
        if (
            self.workspace.allowed_tools is not None
            and call.name not in self.workspace.allowed_tools
        ):
            return self._deny(
                call,
                reason=f"Tool {call.name!r} is not granted to this agent.",
                error="tool_not_granted",
            )
        if call.name in {"read_file", "replace_text", "run_check", RELEASE_PATCH_LEASE_TOOL}:
            path = str(call.arguments.get("path") or "").strip()
            if not path:
                return self._deny(
                    call, reason=f"{call.name} requires a path argument.", error="invalid_arguments"
                )
            try:
                resolved = (self.root / path).resolve()
            except Exception as exc:
                return self._deny(
                    call, reason=f"Invalid path {path!r}: {exc}", error="invalid_path"
                )
            if self.root not in resolved.parents and resolved != self.root:
                return self._deny(
                    call,
                    reason=f"Path {path!r} escapes workspace root {self.root}.",
                    error="path_escape",
                )
            if call.name == RELEASE_PATCH_LEASE_TOOL:
                if self.isolation_manager is None:
                    return self._deny(
                        call,
                        reason="Patch lease release requires an isolation manager.",
                        error="lease_unavailable",
                    )
                release = self.isolation_manager.release_patch_lease(self.owner_id, [path])
                return ToolResult(
                    name=call.name,
                    output={
                        "released": bool(release.released_paths),
                        "released_paths": list(release.released_paths),
                    },
                    success=True,
                    meta={"lease_status": release.status},
                )
            if call.name == "replace_text":
                if not _path_matches_allowlist(path, self.workspace.writable_paths):
                    return self._deny(
                        call,
                        reason=f"Writes to {path!r} are not allowed by workspace policy.",
                        error="write_denied",
                    )
                if self.workspace.enforce_patch_ownership and self.isolation_manager is not None:
                    lease = self.isolation_manager.acquire_patch_lease(self.owner_id, [path])
                    if lease.status == "denied":
                        return self._deny(
                            call,
                            reason=lease.reason
                            or f"Patch ownership for {path!r} is held by another worker.",
                            error="ownership_denied",
                        )
                if self.workspace.approval_mode != "auto":
                    mode = self.workspace.approval_mode
                    label = (
                        "proposal-only mode"
                        if mode == "proposal_only"
                        else "human checkpoint required before applying patch"
                    )
                    return self._proposal_result(
                        call, message=f"Patch proposed for {path!r}; {label}.", approval_mode=mode
                    )
        if call.name == "run_command":
            command = str(call.arguments.get("command") or "").strip()
            if not command:
                return self._deny(
                    call,
                    reason="run_command requires a command argument.",
                    error="invalid_arguments",
                )
            if not _command_allowed(command, self.workspace.runnable_commands):
                return self._deny(
                    call,
                    reason=f"Command {command!r} is not allowed by workspace policy.",
                    error="command_denied",
                )
            return execute_workspace_command(self.root, command, workspace_policy=self.workspace)
        return self.inner.invoke(call)

    def invoke_interop(self, call: ToolCall):
        from .interop import describe_tool_runtime, tool_result_to_operation_result

        result = self.invoke(call)
        op = tool_result_to_operation_result(result, call=call)
        diagnostics = dict(op.diagnostics)
        diagnostics["capability"] = describe_tool_runtime(self)
        return type(op).success(op.value, warnings=op.warnings, diagnostics=diagnostics)


# The coordination-control-plane terminology for the existing policy gate.
# Keep ProgrammingToolRuntime as the established public API.
EnforcingToolRuntime = ProgrammingToolRuntime


def execute_workspace_command(
    root: str | Path, command: str, workspace_policy: WorkspacePolicy | None = None
) -> ToolResult:
    workspace = Path(root).expanduser().resolve()
    if workspace_policy is None:
        return ToolResult(
            name="run_command",
            output="run_command requires an explicit WorkspacePolicy; refusing to execute without one.",
            success=False,
            meta={
                "error": "no_workspace_policy",
                "command": command,
                "cwd": str(workspace),
            },
        )
    policy = workspace_policy
    env, env_keys = _build_command_environment(policy)
    timeout_seconds = max(0.1, float(policy.command_timeout_seconds))
    max_output_chars = max(256, int(policy.max_command_output_chars))
    sandbox = _resolve_command_isolation_backend(policy)
    if sandbox.get("error") is not None:
        return ToolResult(
            name="run_command",
            output=f"Command isolation backend {sandbox.get('requested_backend')!r} is not available.",
            success=False,
            meta={
                "error": str(sandbox.get("error")),
                "command": command,
                "cwd": str(workspace),
                "timeout_seconds": timeout_seconds,
                "environment_keys": env_keys,
                "environment_inherited": bool(policy.inherit_environment),
                "sandbox_requested_backend": sandbox.get("requested_backend"),
                "sandbox_backend": "host",
                "sandbox_external": False,
                "sandbox_fallback_used": bool(sandbox.get("fallback_used")),
                "available_sandbox_backends": list(sandbox.get("available_backends") or []),
            },
        )
    process_group_isolated = os.name == "posix"
    kwargs: dict[str, Any] = {
        "cwd": str(workspace),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True
    if bool(sandbox.get("external")):
        argv = _build_container_command(
            workspace=workspace,
            command=command,
            policy=policy,
            backend=str(sandbox.get("backend") or "docker"),
            env=env,
        )
    else:
        kwargs["env"] = env
        argv = shlex.split(command)
    proc = subprocess.Popen(argv, **kwargs)
    base_meta = {
        "command": command,
        "cwd": str(workspace),
        "timeout_seconds": timeout_seconds,
        "environment_keys": env_keys,
        "environment_inherited": bool(policy.inherit_environment),
        "process_group_isolated": process_group_isolated,
        "sandbox_requested_backend": sandbox.get("requested_backend"),
        "sandbox_backend": sandbox.get("backend"),
        "sandbox_external": bool(sandbox.get("external")),
        "sandbox_fallback_used": bool(sandbox.get("fallback_used")),
        "sandbox_engine_path": sandbox.get("engine_path"),
        "sandbox_image": policy.command_isolation_image if bool(sandbox.get("external")) else None,
        "sandbox_network_enabled": bool(policy.command_isolation_network)
        if bool(sandbox.get("external"))
        else None,
        "sandbox_mount_path": policy.command_isolation_mount_path
        if bool(sandbox.get("external"))
        else None,
        "sandbox_command": list(argv) if bool(sandbox.get("external")) else None,
    }
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        stdout, stderr = proc.communicate()
        stdout_value, stdout_truncated, stdout_length = _truncate_output(
            stdout or "", max_chars=max_output_chars
        )
        stderr_value, stderr_truncated, stderr_length = _truncate_output(
            stderr or "", max_chars=max_output_chars
        )
        meta = dict(base_meta)
        meta.update(
            {
                "error": "command_timeout",
                "stdout": stdout_value,
                "stderr": stderr_value,
                "stdout_length": stdout_length,
                "stderr_length": stderr_length,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            }
        )
        return ToolResult(
            name="run_command",
            output=f"Command timed out after {timeout_seconds:.2f} seconds.",
            success=False,
            meta=meta,
        )
    result = CommandExecutionResult(
        command=command,
        returncode=int(proc.returncode),
        stdout=str(stdout),
        stderr=str(stderr),
    )
    stdout_value, stdout_truncated, stdout_length = _truncate_output(
        result.stdout, max_chars=max_output_chars
    )
    stderr_value, stderr_truncated, stderr_length = _truncate_output(
        result.stderr, max_chars=max_output_chars
    )
    summary = (stdout_value or stderr_value or "").strip()
    if not summary:
        summary = f"command exited with return code {result.returncode}"
    meta = dict(base_meta)
    meta.update(
        {
            "returncode": result.returncode,
            "stdout": stdout_value,
            "stderr": stderr_value,
            "stdout_length": stdout_length,
            "stderr_length": stderr_length,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
    )
    return ToolResult(
        name="run_command",
        output=summary,
        success=result.returncode == 0,
        meta=meta,
    )


@dataclass(frozen=True)
class ContextBudgetConfig:
    max_visible_steps: int = 4
    max_tool_output_chars: int = 160
    summary_max_chars: int = 600
    artifact_dirname: str = "context_artifacts"
    memory_limit: int = 5


@dataclass(frozen=True)
class ProgrammingRoleBindings:
    planner: str | None = None
    executor: str | None = None
    critic: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"planner": self.planner, "executor": self.executor, "critic": self.critic}

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "ProgrammingRoleBindings":
        payload = dict(payload or {})
        return cls(
            planner=payload.get("planner"),
            executor=payload.get("executor"),
            critic=payload.get("critic"),
        )


@dataclass(frozen=True)
class ProgrammingRuntimeConfig:
    task: ProgrammingTask
    memory_backend: str = "engram"
    project_id: str = "agent_programming_demo"
    session_id: str = "programming_demo"
    role_bindings: ProgrammingRoleBindings = field(default_factory=ProgrammingRoleBindings)
    context_budget: ContextBudgetConfig = field(default_factory=ContextBudgetConfig)
    failure_policy: FailurePolicy = field(default_factory=FailurePolicy)
    memory_subdir: str = ".agent_memory"
    state_subdir: str = ".agent_state"
    default_target_path: str = "main.py"
    seed_content: str = "def add(a, b):\n    return a - b\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": {
                "task_id": self.task.task_id,
                "goal": self.task.goal,
                "session_id": self.task.session_id,
                "workspace": asdict(self.task.workspace),
                "plan": [asdict(step) for step in self.task.plan],
                "verification_commands": list(self.task.verification_commands),
                "metadata": dict(self.task.metadata),
            },
            "memory_backend": self.memory_backend,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "role_bindings": self.role_bindings.to_dict(),
            "context_budget": asdict(self.context_budget),
            "failure_policy": asdict(self.failure_policy),
            "memory_subdir": self.memory_subdir,
            "state_subdir": self.state_subdir,
            "default_target_path": self.default_target_path,
            "seed_content": self.seed_content,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProgrammingRuntimeConfig":
        task_payload = dict(payload.get("task") or {})
        workspace_payload = dict(task_payload.get("workspace") or {})
        task = ProgrammingTask(
            task_id=str(task_payload.get("task_id") or "programming_task"),
            goal=str(task_payload.get("goal") or ""),
            session_id=str(
                task_payload.get("session_id") or payload.get("session_id") or "programming_demo"
            ),
            workspace=WorkspacePolicy(**workspace_payload)
            if workspace_payload
            else WorkspacePolicy(),
            plan=[PlanStep(**item) for item in list(task_payload.get("plan") or [])],
            verification_commands=[
                str(item) for item in list(task_payload.get("verification_commands") or [])
            ],
            metadata=dict(task_payload.get("metadata") or {}),
        )
        fp_payload = dict(payload.get("failure_policy") or {})
        raw_tool_policies = list(fp_payload.pop("tool_policies", []) or [])
        tool_policies = [ToolFailurePolicy(**item) for item in raw_tool_policies]
        failure_policy = (
            FailurePolicy(tool_policies=tool_policies, **fp_payload)
            if fp_payload or tool_policies
            else FailurePolicy()
        )
        cb_payload = dict(payload.get("context_budget") or {})
        context_budget = ContextBudgetConfig(**cb_payload) if cb_payload else ContextBudgetConfig()
        return cls(
            task=task,
            memory_backend=str(payload.get("memory_backend") or "engram"),
            project_id=str(payload.get("project_id") or "agent_programming_demo"),
            session_id=str(payload.get("session_id") or task.session_id or "programming_demo"),
            role_bindings=ProgrammingRoleBindings.from_dict(payload.get("role_bindings")),
            context_budget=context_budget,
            failure_policy=failure_policy,
            memory_subdir=str(payload.get("memory_subdir") or ".agent_memory"),
            state_subdir=str(payload.get("state_subdir") or ".agent_state"),
            default_target_path=str(payload.get("default_target_path") or "main.py"),
            seed_content=str(payload.get("seed_content") or "def add(a, b):\n    return a - b\n"),
        )


def load_programming_runtime_config(path: str | Path) -> ProgrammingRuntimeConfig:
    """Load a programming runtime config from JSON or TOML."""
    config_path = Path(path).expanduser()
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    elif suffix == ".toml":
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    else:
        raise ValueError(
            f"Unsupported programming config format: {config_path.suffix or '<none>'}. Use .json or .toml."
        )
    if not isinstance(payload, dict):
        raise ValueError(f"Programming runtime config at {config_path} must decode to an object.")
    return ProgrammingRuntimeConfig.from_dict(payload)


def save_programming_runtime_config(config: ProgrammingRuntimeConfig, path: str | Path) -> Path:
    """Save a programming runtime config to JSON."""
    config_path = Path(path).expanduser()
    if config_path.suffix.lower() != ".json":
        raise ValueError("Programming runtime configs are currently saved as .json files.")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return config_path


def build_programming_task(
    *,
    task_id: str,
    goal: str,
    path: str = "main.py",
    session_id: str = "programming_demo",
    writable_paths: list[str] | None = None,
    verification_commands: list[str] | None = None,
    plan: list[PlanStep] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProgrammingTask:
    writable_paths = list(writable_paths or [path])
    verification_commands = list(verification_commands or [f"run_check:{path}:return a + b"])
    task_metadata = {"path": path, **dict(metadata or {})}
    return ProgrammingTask(
        task_id=task_id,
        goal=goal,
        session_id=session_id,
        workspace=WorkspacePolicy(root=".", writable_paths=writable_paths, approval_mode="auto"),
        plan=list(plan or []),
        verification_commands=verification_commands,
        metadata=task_metadata,
    )


class ProgrammingFailureController(AgentRunLifecycleHook):
    def __init__(
        self, tracker: "ProgrammingStateTracker", *, failure_policy: FailurePolicy | None = None
    ) -> None:
        self.tracker = tracker
        self.failure_policy = failure_policy or FailurePolicy()

    def on_start(self, task: AgentTask, *, max_steps: int, engine_roles: EngineRoles) -> None:
        task.context.pop("_programming_stop", None)
        task.context.pop("_programming_retry_action", None)
        task.context.pop("_programming_next_controller", None)

    def _set_retry(self, task: AgentTask, step: AgentStep, *, reason: str) -> None:
        if step.action.tool_call is None:
            return
        task.context["_programming_retry_action"] = {
            "name": step.action.tool_call.name,
            "arguments": dict(step.action.tool_call.arguments),
            "message": step.action.message or reason,
            "meta": {
                **dict(step.action.meta),
                "retry_reason": reason,
                "retry_attempted": True,
            },
        }

    def _set_stop(self, task: AgentTask, message: str) -> None:
        task.context["_programming_stop"] = {
            "reason": "planner_stop",
            "final_output": message,
        }

    def _set_escalate(self, task: AgentTask, *, message: str) -> None:
        task.context["_programming_next_controller"] = "critic"
        task.context["_programming_policy_note"] = message

    def on_step(
        self, task: AgentTask, context: AgentContext, step: AgentStep, run: AgentRun
    ) -> None:
        observation = step.observation
        if observation is None or observation.tool_result is None or step.action.tool_call is None:
            return

        result = observation.tool_result
        tool_name = result.name
        policy = self.failure_policy.policy_for(tool_name)
        step_id = str(step.action.meta.get("plan_step_id") or "").strip()
        retries = self.tracker.state.retry_counts.get(step_id, 0) if step_id else 0
        text = str(result.output or "")
        is_empty = text.strip() == ""
        if is_empty and policy.empty_behavior != "ignore":
            if policy.empty_behavior == "retry" and retries <= policy.max_retries:
                self._set_retry(task, step, reason=f"Retry {tool_name} after empty result.")
                return
            if policy.empty_behavior == "escalate":
                self._set_escalate(task, message=f"Escalate after empty result from {tool_name}.")
                return
            self._set_stop(task, f"Stopped after empty result from {tool_name}.")
            return

        if not result.success:
            if policy.failure_behavior == "retry" and retries <= policy.max_retries:
                self._set_retry(task, step, reason=f"Retry {tool_name} after failure.")
                return
            if policy.failure_behavior == "escalate":
                self._set_escalate(task, message=f"Escalate after failure from {tool_name}.")
                return
            self._set_stop(task, f"Stopped after failure from {tool_name}: {text}")

    def on_finish(self, run: AgentRun) -> None:
        run.task.context.pop("_programming_retry_action", None)


class ProgrammingContextManager:
    def __init__(self, root: str | Path, *, config: ContextBudgetConfig | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = config or ContextBudgetConfig()
        self.artifact_root = self.root / self.config.artifact_dirname
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _artifact_path(self, task: AgentTask, step: AgentStep) -> Path:
        safe_task = str(task.task_id or task.session_id or "task").strip().replace("/", "_")
        tool_name = (
            step.action.tool_call.name if step.action.tool_call is not None else step.action.kind
        )
        return self.artifact_root / f"{safe_task}_step{step.index}_{tool_name}.txt"

    def _truncate_text(
        self, text: str, *, task: AgentTask, step: AgentStep
    ) -> tuple[str, dict[str, Any] | None]:
        raw = str(text or "")
        if len(raw) <= self.config.max_tool_output_chars:
            return raw, None
        path = self._artifact_path(task, step)
        path.write_text(raw, encoding="utf-8")
        head = raw[: self.config.max_tool_output_chars // 2].rstrip()
        tail = raw[-self.config.max_tool_output_chars // 2 :].lstrip()
        truncated = f"{head}\n... [full output stored at {path}] ...\n{tail}"
        return truncated, {"path": str(path), "chars": len(raw), "step_index": step.index}

    def _compact_step(self, task: AgentTask, step: AgentStep) -> tuple[str, dict[str, Any] | None]:
        if step.observation is not None:
            text = step.observation.text
        elif step.action.final_output:
            text = step.action.final_output
        else:
            text = step.action.message
        text = str(text or "")
        truncated, artifact = self._truncate_text(text, task=task, step=step)
        label = (
            step.action.tool_call.name if step.action.tool_call is not None else step.action.kind
        )
        return f"step {step.index}: {label} -> {truncated}", artifact

    def _compact_history(
        self, task: AgentTask, steps: Sequence[AgentStep]
    ) -> tuple[list[str], list[dict[str, Any]]]:
        lines: list[str] = []
        artifacts: list[dict[str, Any]] = []
        for step in steps:
            line, artifact = self._compact_step(task, step)
            lines.append(line)
            if artifact is not None:
                artifacts.append(artifact)
        return lines, artifacts

    def _visible_steps(
        self, task: AgentTask, steps: Sequence[AgentStep]
    ) -> tuple[list[AgentStep], list[dict[str, Any]]]:
        visible: list[AgentStep] = []
        artifacts: list[dict[str, Any]] = []
        for step in steps:
            observation = step.observation
            if observation is not None and observation.tool_result is not None:
                truncated, artifact = self._truncate_text(observation.text, task=task, step=step)
                tool_result = ToolResult(
                    name=observation.tool_result.name,
                    output=truncated,
                    success=observation.tool_result.success,
                    meta=dict(observation.tool_result.meta),
                )
                observation = AgentObservation(
                    kind=observation.kind,
                    text=truncated,
                    tool_result=tool_result,
                    meta=dict(observation.meta),
                )
                if artifact is not None:
                    artifacts.append(artifact)
            visible.append(
                AgentStep(
                    index=step.index, action=step.action, observation=observation, trace=step.trace
                )
            )
        return visible, artifacts

    def build_context(
        self,
        task: AgentTask,
        steps: Sequence[AgentStep],
        *,
        active_controller: str,
        escalated: bool,
        memory: Any,
        tool_specs: Sequence[ToolSpec],
        engine_roles: EngineRoles,
    ) -> AgentContext:
        recent = list(steps)[-self.config.max_visible_steps :]
        compacted = (
            list(steps)[: -self.config.max_visible_steps]
            if len(steps) > self.config.max_visible_steps
            else []
        )
        compacted_lines, compacted_artifacts = self._compact_history(task, compacted)
        visible_steps, visible_artifacts = self._visible_steps(task, recent)
        history_summary = "\n".join(compacted_lines)
        if len(history_summary) > self.config.summary_max_chars:
            history_summary = (
                history_summary[: self.config.summary_max_chars].rstrip()
                + "\n... [history compacted]"
            )
        budget = {
            "visible_step_count": len(visible_steps),
            "compacted_step_count": len(compacted),
            "history_summary": history_summary,
            "artifacts": compacted_artifacts + visible_artifacts,
            "preserved_fields": ["goal", "workspace_policy", "programming_state", "failure_policy"],
        }
        managed_task = AgentTask(
            task_id=task.task_id,
            goal=task.goal,
            session_id=task.session_id,
            context={**dict(task.context), "context_budget": budget},
        )
        recalled = memory.recall(managed_task, visible_steps, limit=self.config.memory_limit)
        trace_recall = getattr(memory, "trace_recall", None)
        memory_trace = (
            trace_recall(managed_task, visible_steps, limit=self.config.memory_limit)
            if callable(trace_recall)
            else None
        )
        return AgentContext(
            task=managed_task,
            steps=visible_steps,
            recalled=recalled,
            memory_trace=memory_trace,
            tool_specs=list(tool_specs),
            engine_roles=engine_roles,
            active_controller=active_controller,
            escalated=escalated,
        )
