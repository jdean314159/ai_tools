from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
import shlex
import shutil
import signal
import subprocess
from typing import Any, Literal, Sequence

from .contracts import AgentContext, AgentObservation, AgentRun, AgentRunLifecycleHook, AgentStep, AgentTask, EngineRoles, ToolCall, ToolResult, ToolSpec, ToolRuntime

PlanStatus = Literal["pending", "in_progress", "completed", "failed"]
ApprovalMode = Literal["auto", "proposal_only", "human_checkpoint"]
IsolationMode = Literal["in_place", "branch", "worktree"]
SandboxBackend = Literal["host", "auto", "docker", "podman"]


DEFAULT_ALLOWED_ENVIRONMENT_KEYS = [
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONPATH",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "USERNAME",
    "VIRTUAL_ENV",
    "WINDIR",
]


@dataclass(frozen=True)
class WorkspacePolicy:
    root: str = "."
    writable_paths: list[str] = field(default_factory=list)
    runnable_commands: list[str] = field(default_factory=list)
    approval_mode: ApprovalMode = "auto"
    max_parallel_patch_workers: int = 1
    isolation_mode: IsolationMode = "in_place"
    branch_prefix: str = "agent/"
    enforce_patch_ownership: bool = True
    command_timeout_seconds: float = 30.0
    max_command_output_chars: int = 12000
    inherit_environment: bool = False
    allowed_environment_keys: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_ENVIRONMENT_KEYS))
    denied_environment_keys: list[str] = field(default_factory=list)
    command_isolation_backend: SandboxBackend = "host"
    command_isolation_image: str = "python:3.12-slim"
    command_isolation_network: bool = False
    command_isolation_fallback_to_host: bool = False
    command_isolation_extra_args: list[str] = field(default_factory=list)
    command_isolation_mount_path: str = "/workspace"


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    description: str
    status: PlanStatus = "pending"
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VerificationResult:
    step_id: str
    success: bool
    summary: str
    command: str | None = None


@dataclass(frozen=True)
class PatchProposal:
    path: str
    old: str
    new: str
    rationale: str = ""
    status: Literal["proposed", "applied", "rejected"] = "proposed"


@dataclass(frozen=True)
class ToolFailurePolicy:
    tool_name: str
    max_retries: int = 0
    failure_behavior: Literal["retry", "escalate", "stop"] = "stop"
    empty_behavior: Literal["retry", "escalate", "stop", "ignore"] = "stop"
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class FailurePolicy:
    max_retries_per_step: int = 2
    stop_on_repeated_tool_calls: int = 2
    retryable_tools: list[str] = field(default_factory=lambda: ["read_file", "replace_text", "run_check", "run_command"])
    stop_on_empty_result: bool = True
    tool_policies: list[ToolFailurePolicy] = field(
        default_factory=lambda: [
            ToolFailurePolicy("read_file", max_retries=1, failure_behavior="retry", empty_behavior="stop"),
            ToolFailurePolicy("replace_text", max_retries=1, failure_behavior="retry", empty_behavior="retry"),
            ToolFailurePolicy("run_check", max_retries=0, failure_behavior="escalate", empty_behavior="escalate"),
            ToolFailurePolicy("run_command", max_retries=0, failure_behavior="escalate", empty_behavior="escalate"),
        ]
    )

    def policy_for(self, tool_name: str) -> ToolFailurePolicy:
        normalized = str(tool_name or "").strip()
        for policy in self.tool_policies:
            if policy.tool_name == normalized:
                return policy
        default_behavior: Literal["retry", "escalate", "stop"] = "retry" if normalized in self.retryable_tools else "stop"
        return ToolFailurePolicy(
            tool_name=normalized or "tool",
            max_retries=self.max_retries_per_step if normalized in self.retryable_tools else 0,
            failure_behavior=default_behavior,
            empty_behavior="stop" if self.stop_on_empty_result else "ignore",
        )






def _normalize_rel_path(path: str) -> str:
    raw = str(path or '').strip().replace('\\', '/')
    if not raw:
        return ''
    normalized = os.path.normpath(raw).replace('\\', '/')
    while normalized.startswith('./'):
        normalized = normalized[2:]
    if normalized == '.':
        return ''
    return normalized


def _path_matches_allowlist(path: str, allowed: Sequence[str]) -> bool:
    normalized = _normalize_rel_path(path)
    if not normalized:
        return False
    for raw in allowed:
        candidate = _normalize_rel_path(str(raw or ''))
        if not candidate:
            continue
        if normalized == candidate or normalized.startswith(candidate + '/'):
            return True
    return False


def _command_allowed(command: str, allowed: Sequence[str]) -> bool:
    normalized = ' '.join(shlex.split(str(command or '').strip())) if str(command or '').strip() else ''
    if not normalized:
        return False
    allowed_norm = []
    for item in allowed:
        raw = str(item or '').strip()
        if not raw:
            continue
        allowed_norm.append(' '.join(shlex.split(raw)))
    return normalized in allowed_norm


def _build_command_environment(policy: WorkspacePolicy) -> tuple[dict[str, str], list[str]]:
    denied = {str(key).strip() for key in policy.denied_environment_keys if str(key).strip()}
    allowed = [str(key).strip() for key in policy.allowed_environment_keys if str(key).strip()]
    if policy.inherit_environment:
        env = {key: value for key, value in os.environ.items() if key not in denied}
    else:
        env = {}
        for key in allowed:
            if key in denied:
                continue
            value = os.environ.get(key)
            if value is not None:
                env[key] = value
    return env, sorted(env.keys())


def _truncate_output(text: str, *, max_chars: int) -> tuple[str, bool, int]:
    value = str(text or '')
    length = len(value)
    if max_chars <= 0 or length <= max_chars:
        return value, False, length
    if max_chars <= 32:
        clipped = value[:max_chars]
    else:
        head = max_chars - 32
        clipped = value[:head] + "\n...[output truncated]...\n"
    return clipped, True, length


def _resolve_command_isolation_backend(policy: WorkspacePolicy) -> dict[str, Any]:
    requested = str(getattr(policy, 'command_isolation_backend', 'host') or 'host').strip().lower()
    if not requested:
        requested = 'host'
    result: dict[str, Any] = {
        'requested_backend': requested,
        'backend': 'host',
        'external': False,
        'fallback_used': False,
        'engine_path': None,
        'error': None,
        'available_backends': [name for name in ('docker', 'podman') if shutil.which(name)],
    }
    if requested == 'host':
        return result
    candidates = []
    if requested == 'auto':
        candidates = ['docker', 'podman']
    elif requested in {'docker', 'podman'}:
        candidates = [requested]
    else:
        result['error'] = 'invalid_sandbox_backend'
        return result
    for candidate in candidates:
        engine_path = shutil.which(candidate)
        if engine_path:
            result.update({'backend': candidate, 'external': True, 'engine_path': engine_path})
            return result
    if bool(getattr(policy, 'command_isolation_fallback_to_host', False)):
        result['fallback_used'] = True
        return result
    result['error'] = 'sandbox_unavailable'
    return result


def _build_container_command(
    *,
    workspace: Path,
    command: str,
    policy: WorkspacePolicy,
    backend: str,
    env: dict[str, str],
) -> list[str]:
    mount_path = str(getattr(policy, 'command_isolation_mount_path', '/workspace') or '/workspace').strip() or '/workspace'
    image = str(getattr(policy, 'command_isolation_image', 'python:3.12-slim') or 'python:3.12-slim').strip() or 'python:3.12-slim'
    argv: list[str] = [backend, 'run', '--rm', '--workdir', mount_path, '--volume', f'{workspace}:{mount_path}']
    if not bool(getattr(policy, 'command_isolation_network', False)):
        argv.extend(['--network', 'none'])
    if os.name == 'posix' and hasattr(os, 'getuid') and hasattr(os, 'getgid'):
        argv.extend(['--user', f'{os.getuid()}:{os.getgid()}'])
    for key, value in env.items():
        argv.extend(['-e', f'{key}={value}'])
    for item in list(getattr(policy, 'command_isolation_extra_args', []) or []):
        raw = str(item or '').strip()
        if raw:
            argv.append(raw)
    argv.append(image)
    argv.extend(['/bin/sh', '-lc', command])
    return argv


@dataclass(frozen=True)
class CommandExecutionResult:
    command: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class WorkspaceAllocation:
    owner_id: str
    root: str
    isolation_mode: IsolationMode
    source: str = "in_place"
    branch_name: str | None = None


@dataclass(frozen=True)
class PatchOwnership:
    owner_id: str
    paths: list[str]
    status: Literal["active", "released", "denied"] = "active"
    reason: str = ""


class WorkspaceIsolationManager:
    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.workspaces_root = self.state_root / "workspaces"
        self.workspaces_root.mkdir(parents=True, exist_ok=True)
        self._allocations_path = self.state_root / "workspace_allocations.json"
        self._leases_path = self.state_root / "patch_leases.json"

    def _safe_owner(self, owner_id: str) -> str:
        return str(owner_id or "worker").strip().replace("/", "_") or "worker"

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def _save_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _is_git_repo(self, root: Path) -> bool:
        if shutil.which("git") is None:
            return False
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, check=False)
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def _prepare_git_worktree(self, base_root: Path, owner_id: str, policy: WorkspacePolicy, target: Path, *, mode: IsolationMode) -> WorkspaceAllocation | None:
        if mode not in {"branch", "worktree"} or not self._is_git_repo(base_root):
            return None
        branch_name = f"{policy.branch_prefix}{self._safe_owner(owner_id)}"
        if not target.exists():
            proc = subprocess.run(
                ["git", "-C", str(base_root), "worktree", "add", "--force", "-B", branch_name, str(target), "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                return None
        return WorkspaceAllocation(owner_id=owner_id, root=str(target), isolation_mode=mode, source="git_worktree", branch_name=branch_name)

    def _prepare_copy_workspace(self, base_root: Path, owner_id: str, target: Path, *, mode: IsolationMode) -> WorkspaceAllocation:
        if not target.exists():
            ignore_names = {self.state_root.name, "__pycache__", ".pytest_cache"}
            shutil.copytree(base_root, target, ignore=shutil.ignore_patterns(*ignore_names))
        return WorkspaceAllocation(owner_id=owner_id, root=str(target), isolation_mode=mode, source="copy")

    def prepare_workspace(self, base_root: str | Path, owner_id: str, policy: WorkspacePolicy) -> WorkspaceAllocation:
        base = Path(base_root).expanduser().resolve()
        mode = policy.isolation_mode
        if mode == "in_place":
            allocation = WorkspaceAllocation(owner_id=owner_id, root=str(base), isolation_mode=mode, source="in_place")
            data = self._load_json(self._allocations_path)
            data[self._safe_owner(owner_id)] = asdict(allocation)
            self._save_json(self._allocations_path, data)
            return allocation

        target = self.workspaces_root / self._safe_owner(owner_id)
        allocation = self._prepare_git_worktree(base, owner_id, policy, target, mode=mode)
        if allocation is None:
            allocation = self._prepare_copy_workspace(base, owner_id, target, mode=mode)
        data = self._load_json(self._allocations_path)
        data[self._safe_owner(owner_id)] = asdict(allocation)
        self._save_json(self._allocations_path, data)
        return allocation

    def active_patch_owners(self) -> dict[str, dict[str, Any]]:
        return self._load_json(self._leases_path)

    def acquire_patch_lease(self, owner_id: str, paths: Sequence[str]) -> PatchOwnership:
        normalized = [_normalize_rel_path(path) for path in paths if _normalize_rel_path(path)]
        leases = self.active_patch_owners()
        for path in normalized:
            existing = dict(leases.get(path) or {})
            if existing and existing.get("status") == "active" and existing.get("owner_id") != owner_id:
                return PatchOwnership(owner_id=owner_id, paths=normalized, status="denied", reason=f"{path} is currently owned by {existing.get('owner_id')}")
        for path in normalized:
            leases[path] = {"owner_id": owner_id, "status": "active"}
        self._save_json(self._leases_path, leases)
        return PatchOwnership(owner_id=owner_id, paths=normalized, status="active")

    def release_patch_lease(self, owner_id: str, paths: Sequence[str]) -> PatchOwnership:
        normalized = [_normalize_rel_path(path) for path in paths if _normalize_rel_path(path)]
        leases = self.active_patch_owners()
        for path in normalized:
            existing = dict(leases.get(path) or {})
            if existing.get("owner_id") == owner_id:
                leases[path] = {"owner_id": owner_id, "status": "released"}
        self._save_json(self._leases_path, leases)
        return PatchOwnership(owner_id=owner_id, paths=normalized, status="released")


class ProgrammingToolRuntime:
    def __init__(self, inner: ToolRuntime, workspace: WorkspacePolicy, *, root: str | Path, owner_id: str = "worker", isolation_manager: WorkspaceIsolationManager | None = None) -> None:
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
        return self.inner.list_tools()

    def _deny(self, call: ToolCall, *, reason: str, error: str = 'policy_violation') -> ToolResult:
        return ToolResult(name=call.name, output=reason, success=False, meta={'error': error, 'policy_reason': reason})

    def _proposal_result(self, call: ToolCall, *, message: str, approval_mode: ApprovalMode) -> ToolResult:
        return ToolResult(
            name=call.name,
            output=message,
            success=True,
            meta={
                'approval_required': True,
                'approval_mode': approval_mode,
                'patch_status': 'proposed',
                'patch_proposal': dict(call.arguments),
            },
        )

    def invoke(self, call: ToolCall) -> ToolResult:
        if call.name in {'read_file', 'replace_text', 'run_check'}:
            path = str(call.arguments.get('path') or '').strip()
            if not path:
                return self._deny(call, reason=f'{call.name} requires a path argument.', error='invalid_arguments')
            try:
                resolved = (self.root / path).resolve()
            except Exception as exc:
                return self._deny(call, reason=f'Invalid path {path!r}: {exc}', error='invalid_path')
            if self.root not in resolved.parents and resolved != self.root:
                return self._deny(call, reason=f'Path {path!r} escapes workspace root {self.root}.', error='path_escape')
            if call.name == 'replace_text':
                if not _path_matches_allowlist(path, self.workspace.writable_paths):
                    return self._deny(call, reason=f'Writes to {path!r} are not allowed by workspace policy.', error='write_denied')
                if self.workspace.enforce_patch_ownership and self.isolation_manager is not None:
                    lease = self.isolation_manager.acquire_patch_lease(self.owner_id, [path])
                    if lease.status == 'denied':
                        return self._deny(call, reason=lease.reason or f'Patch ownership for {path!r} is held by another worker.', error='ownership_denied')
                if self.workspace.approval_mode != 'auto':
                    mode = self.workspace.approval_mode
                    label = 'proposal-only mode' if mode == 'proposal_only' else 'human checkpoint required before applying patch'
                    return self._proposal_result(call, message=f'Patch proposed for {path!r}; {label}.', approval_mode=mode)
        if call.name == 'run_command':
            command = str(call.arguments.get('command') or '').strip()
            if not command:
                return self._deny(call, reason='run_command requires a command argument.', error='invalid_arguments')
            if not _command_allowed(command, self.workspace.runnable_commands):
                return self._deny(call, reason=f'Command {command!r} is not allowed by workspace policy.', error='command_denied')
            return execute_workspace_command(self.root, command, workspace_policy=self.workspace)
        return self.inner.invoke(call)

    def invoke_interop(self, call: ToolCall):
        from .interop import describe_tool_runtime, tool_result_to_operation_result
        result = self.invoke(call)
        op = tool_result_to_operation_result(result, call=call)
        diagnostics = dict(op.diagnostics)
        diagnostics['capability'] = describe_tool_runtime(self)
        return type(op).success(op.value, warnings=op.warnings, diagnostics=diagnostics)


def execute_workspace_command(root: str | Path, command: str, workspace_policy: WorkspacePolicy | None = None) -> ToolResult:
    workspace = Path(root).expanduser().resolve()
    policy = workspace_policy or WorkspacePolicy(root=str(workspace), runnable_commands=[command])
    env, env_keys = _build_command_environment(policy)
    timeout_seconds = max(0.1, float(policy.command_timeout_seconds))
    max_output_chars = max(256, int(policy.max_command_output_chars))
    sandbox = _resolve_command_isolation_backend(policy)
    if sandbox.get('error') is not None:
        return ToolResult(
            name='run_command',
            output=f"Command isolation backend {sandbox.get('requested_backend')!r} is not available.",
            success=False,
            meta={
                'error': str(sandbox.get('error')),
                'command': command,
                'cwd': str(workspace),
                'timeout_seconds': timeout_seconds,
                'environment_keys': env_keys,
                'environment_inherited': bool(policy.inherit_environment),
                'sandbox_requested_backend': sandbox.get('requested_backend'),
                'sandbox_backend': 'host',
                'sandbox_external': False,
                'sandbox_fallback_used': bool(sandbox.get('fallback_used')),
                'available_sandbox_backends': list(sandbox.get('available_backends') or []),
            },
        )
    process_group_isolated = os.name == 'posix'
    kwargs: dict[str, Any] = {
        'cwd': str(workspace),
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'text': True,
    }
    if os.name == 'posix':
        kwargs['start_new_session'] = True
    if bool(sandbox.get('external')):
        argv = _build_container_command(
            workspace=workspace,
            command=command,
            policy=policy,
            backend=str(sandbox.get('backend') or 'docker'),
            env=env,
        )
    else:
        kwargs['env'] = env
        argv = shlex.split(command)
    proc = subprocess.Popen(argv, **kwargs)
    base_meta = {
        'command': command,
        'cwd': str(workspace),
        'timeout_seconds': timeout_seconds,
        'environment_keys': env_keys,
        'environment_inherited': bool(policy.inherit_environment),
        'process_group_isolated': process_group_isolated,
        'sandbox_requested_backend': sandbox.get('requested_backend'),
        'sandbox_backend': sandbox.get('backend'),
        'sandbox_external': bool(sandbox.get('external')),
        'sandbox_fallback_used': bool(sandbox.get('fallback_used')),
        'sandbox_engine_path': sandbox.get('engine_path'),
        'sandbox_image': policy.command_isolation_image if bool(sandbox.get('external')) else None,
        'sandbox_network_enabled': bool(policy.command_isolation_network) if bool(sandbox.get('external')) else None,
        'sandbox_mount_path': policy.command_isolation_mount_path if bool(sandbox.get('external')) else None,
        'sandbox_command': list(argv) if bool(sandbox.get('external')) else None,
    }
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        stdout, stderr = proc.communicate()
        stdout_value, stdout_truncated, stdout_length = _truncate_output(stdout or '', max_chars=max_output_chars)
        stderr_value, stderr_truncated, stderr_length = _truncate_output(stderr or '', max_chars=max_output_chars)
        meta = dict(base_meta)
        meta.update({
            'error': 'command_timeout',
            'stdout': stdout_value,
            'stderr': stderr_value,
            'stdout_length': stdout_length,
            'stderr_length': stderr_length,
            'stdout_truncated': stdout_truncated,
            'stderr_truncated': stderr_truncated,
        })
        return ToolResult(
            name='run_command',
            output=f'Command timed out after {timeout_seconds:.2f} seconds.',
            success=False,
            meta=meta,
        )
    result = CommandExecutionResult(
        command=command,
        returncode=int(proc.returncode),
        stdout=str(stdout),
        stderr=str(stderr),
    )
    stdout_value, stdout_truncated, stdout_length = _truncate_output(result.stdout, max_chars=max_output_chars)
    stderr_value, stderr_truncated, stderr_length = _truncate_output(result.stderr, max_chars=max_output_chars)
    summary = (stdout_value or stderr_value or '').strip()
    if not summary:
        summary = f'command exited with return code {result.returncode}'
    meta = dict(base_meta)
    meta.update({
        'returncode': result.returncode,
        'stdout': stdout_value,
        'stderr': stderr_value,
        'stdout_length': stdout_length,
        'stderr_length': stderr_length,
        'stdout_truncated': stdout_truncated,
        'stderr_truncated': stderr_truncated,
    })
    return ToolResult(
        name='run_command',
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
class ProgrammingTask:
    task_id: str
    goal: str
    session_id: str = "default"
    workspace: WorkspacePolicy = field(default_factory=WorkspacePolicy)
    plan: list[PlanStep] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_agent_task(self) -> AgentTask:
        return AgentTask(
            task_id=self.task_id,
            goal=self.goal,
            session_id=self.session_id,
            context={
                "workspace_policy": asdict(self.workspace),
                "plan": [asdict(step) for step in self.plan],
                "verification_commands": list(self.verification_commands),
                **dict(self.metadata),
            },
        )



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
        return cls(planner=payload.get("planner"), executor=payload.get("executor"), critic=payload.get("critic"))


@dataclass(frozen=True)
class ProgrammingRuntimeConfig:
    task: ProgrammingTask
    memory_backend: str = "engram_lite"
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
            session_id=str(task_payload.get("session_id") or payload.get("session_id") or "programming_demo"),
            workspace=WorkspacePolicy(**workspace_payload) if workspace_payload else WorkspacePolicy(),
            plan=[PlanStep(**item) for item in list(task_payload.get("plan") or [])],
            verification_commands=[str(item) for item in list(task_payload.get("verification_commands") or [])],
            metadata=dict(task_payload.get("metadata") or {}),
        )
        fp_payload = dict(payload.get("failure_policy") or {})
        raw_tool_policies = list(fp_payload.pop("tool_policies", []) or [])
        tool_policies = [ToolFailurePolicy(**item) for item in raw_tool_policies]
        failure_policy = FailurePolicy(tool_policies=tool_policies, **fp_payload) if fp_payload or tool_policies else FailurePolicy()
        cb_payload = dict(payload.get("context_budget") or {})
        context_budget = ContextBudgetConfig(**cb_payload) if cb_payload else ContextBudgetConfig()
        return cls(
            task=task,
            memory_backend=str(payload.get("memory_backend") or "engram_lite"),
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
        raise ValueError(f"Unsupported programming config format: {config_path.suffix or '<none>'}. Use .json or .toml.")
    if not isinstance(payload, dict):
        raise ValueError(f"Programming runtime config at {config_path} must decode to an object.")
    return ProgrammingRuntimeConfig.from_dict(payload)


def save_programming_runtime_config(config: ProgrammingRuntimeConfig, path: str | Path) -> Path:
    """Save a programming runtime config to JSON."""
    config_path = Path(path).expanduser()
    if config_path.suffix.lower() != ".json":
        raise ValueError("Programming runtime configs are currently saved as .json files.")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    def __init__(self, tracker: "ProgrammingStateTracker", *, failure_policy: FailurePolicy | None = None) -> None:
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

    def on_step(self, task: AgentTask, context: AgentContext, step: AgentStep, run: AgentRun) -> None:
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
        tool_name = step.action.tool_call.name if step.action.tool_call is not None else step.action.kind
        return self.artifact_root / f"{safe_task}_step{step.index}_{tool_name}.txt"

    def _truncate_text(self, text: str, *, task: AgentTask, step: AgentStep) -> tuple[str, dict[str, Any] | None]:
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
        label = step.action.tool_call.name if step.action.tool_call is not None else step.action.kind
        return f"step {step.index}: {label} -> {truncated}", artifact

    def _compact_history(self, task: AgentTask, steps: Sequence[AgentStep]) -> tuple[list[str], list[dict[str, Any]]]:
        lines: list[str] = []
        artifacts: list[dict[str, Any]] = []
        for step in steps:
            line, artifact = self._compact_step(task, step)
            lines.append(line)
            if artifact is not None:
                artifacts.append(artifact)
        return lines, artifacts

    def _visible_steps(self, task: AgentTask, steps: Sequence[AgentStep]) -> tuple[list[AgentStep], list[dict[str, Any]]]:
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
            visible.append(AgentStep(index=step.index, action=step.action, observation=observation, trace=step.trace))
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
        compacted = list(steps)[:-self.config.max_visible_steps] if len(steps) > self.config.max_visible_steps else []
        compacted_lines, compacted_artifacts = self._compact_history(task, compacted)
        visible_steps, visible_artifacts = self._visible_steps(task, recent)
        history_summary = "\n".join(compacted_lines)
        if len(history_summary) > self.config.summary_max_chars:
            history_summary = history_summary[: self.config.summary_max_chars].rstrip() + "\n... [history compacted]"
        budget = {
            "visible_step_count": len(visible_steps),
            "compacted_step_count": len(compacted),
            "history_summary": history_summary,
            "artifacts": compacted_artifacts + visible_artifacts,
            "preserved_fields": ["goal", "workspace_policy", "programming_state", "failure_policy"],
        }
        managed_task = AgentTask(task_id=task.task_id, goal=task.goal, session_id=task.session_id, context={**dict(task.context), "context_budget": budget})
        recalled = memory.recall(managed_task, visible_steps, limit=self.config.memory_limit)
        trace_recall = getattr(memory, "trace_recall", None)
        memory_trace = trace_recall(managed_task, visible_steps, limit=self.config.memory_limit) if callable(trace_recall) else None
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

@dataclass
class ProgrammingTaskState:
    task_id: str
    goal: str
    session_id: str
    status: str = "pending"
    current_step_id: str | None = None
    plan: list[PlanStep] = field(default_factory=list)
    step_count: int = 0
    retry_counts: dict[str, int] = field(default_factory=dict)
    touched_files: list[str] = field(default_factory=list)
    repeated_tool_calls: dict[str, int] = field(default_factory=dict)
    last_verification: VerificationResult | None = None
    last_patch: PatchProposal | None = None
    last_error: str | None = None
    last_policy_decision: str | None = None
    context_window_index: int = 0
    final_output: str | None = None
    escalations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "session_id": self.session_id,
            "status": self.status,
            "current_step_id": self.current_step_id,
            "plan": [asdict(step) for step in self.plan],
            "step_count": self.step_count,
            "retry_counts": dict(self.retry_counts),
            "touched_files": list(self.touched_files),
            "repeated_tool_calls": dict(self.repeated_tool_calls),
            "last_verification": asdict(self.last_verification) if self.last_verification is not None else None,
            "last_patch": asdict(self.last_patch) if self.last_patch is not None else None,
            "last_error": self.last_error,
            "last_policy_decision": self.last_policy_decision,
            "context_window_index": self.context_window_index,
            "final_output": self.final_output,
            "escalations": self.escalations,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProgrammingTaskState":
        plan = [PlanStep(**item) for item in list(payload.get("plan") or [])]
        last_verification = payload.get("last_verification")
        last_patch = payload.get("last_patch")
        return cls(
            task_id=str(payload.get("task_id") or ""),
            goal=str(payload.get("goal") or ""),
            session_id=str(payload.get("session_id") or "default"),
            status=str(payload.get("status") or "pending"),
            current_step_id=payload.get("current_step_id"),
            plan=plan,
            step_count=int(payload.get("step_count") or 0),
            retry_counts={str(k): int(v) for k, v in dict(payload.get("retry_counts") or {}).items()},
            touched_files=[str(item) for item in list(payload.get("touched_files") or [])],
            repeated_tool_calls={str(k): int(v) for k, v in dict(payload.get("repeated_tool_calls") or {}).items()},
            last_verification=VerificationResult(**last_verification) if isinstance(last_verification, dict) else None,
            last_patch=PatchProposal(**last_patch) if isinstance(last_patch, dict) else None,
            last_error=payload.get("last_error"),
            last_policy_decision=payload.get("last_policy_decision"),
            context_window_index=int(payload.get("context_window_index") or 0),
            final_output=payload.get("final_output"),
            escalations=int(payload.get("escalations") or 0),
        )


class ProgrammingTaskStateStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        safe = str(task_id or "task").strip().replace("/", "_")
        return self.root / f"{safe}.json"

    def load(self, task_id: str) -> ProgrammingTaskState | None:
        path = self.path_for(task_id)
        if not path.exists():
            return None
        return ProgrammingTaskState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, state: ProgrammingTaskState) -> ProgrammingTaskState:
        path = self.path_for(state.task_id)
        path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return state

    def initialize(self, task: ProgrammingTask) -> ProgrammingTaskState:
        existing = self.load(task.task_id)
        if existing is not None:
            return existing
        state = ProgrammingTaskState(
            task_id=task.task_id,
            goal=task.goal,
            session_id=task.session_id,
            status="running",
            plan=list(task.plan),
        )
        return self.save(state)


class ProgrammingStateTracker:
    def __init__(self, store: ProgrammingTaskStateStore, task: ProgrammingTask, *, failure_policy: FailurePolicy | None = None) -> None:
        self.store = store
        self.task = task
        self.failure_policy = failure_policy or FailurePolicy()
        self.state = self.store.initialize(task)

    def _touch_file(self, path: str) -> None:
        norm = str(path).strip()
        if norm and norm not in self.state.touched_files:
            self.state.touched_files.append(norm)

    def _set_step_status(self, step_id: str | None, status: PlanStatus, note: str | None = None) -> None:
        if not step_id:
            return
        updated: list[PlanStep] = []
        for step in self.state.plan:
            if step.step_id != step_id:
                updated.append(step)
                continue
            notes = list(step.notes)
            if note and note not in notes:
                notes.append(note)
            updated.append(PlanStep(step_id=step.step_id, description=step.description, status=status, notes=notes))
        self.state.plan = updated
        self.state.current_step_id = step_id

    def attach_to_context(self, context: dict[str, Any]) -> dict[str, Any]:
        out = dict(context)
        out["programming_state"] = self.state.to_dict()
        out["failure_policy"] = asdict(self.failure_policy)
        return out

    def on_start(self, task: AgentTask, *, max_steps: int, engine_roles: Any) -> None:
        self.state.status = "running"
        if self.state.step_count > 0:
            self.state.context_window_index += 1
        policy_note = str(task.context.get("_programming_policy_note") or "").strip()
        if policy_note:
            self.state.last_policy_decision = policy_note
        task.context.update(self.attach_to_context(task.context))
        self.store.save(self.state)


    def on_step(self, task: AgentTask, context: AgentContext, step: AgentStep, run: AgentRun) -> None:
        self.state.step_count = len(run.steps)
        self.state.escalations = run.escalations
        step_id = str(step.action.meta.get("plan_step_id") or "").strip() or None
        if step_id is not None:
            self._set_step_status(step_id, "in_progress")

        if step.action.tool_call is not None:
            call = step.action.tool_call
            signature = f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}"
            self.state.repeated_tool_calls[signature] = self.state.repeated_tool_calls.get(signature, 0) + 1
            path = call.arguments.get("path")
            if isinstance(path, str):
                self._touch_file(path)
            if call.name == "replace_text":
                patch_status = "proposed"
                if step.observation and step.observation.tool_result and step.observation.tool_result.success:
                    patch_status = str(step.observation.tool_result.meta.get("patch_status") or "applied")
                self.state.last_patch = PatchProposal(
                    path=str(call.arguments.get("path") or ""),
                    old=str(call.arguments.get("old") or ""),
                    new=str(call.arguments.get("new") or ""),
                    rationale=str(step.action.message or ""),
                    status=patch_status if patch_status in {"proposed", "applied", "rejected"} else "proposed",
                )

        if step.observation and step.observation.tool_result is not None:
            tool_result = step.observation.tool_result
            if tool_result.name in {"run_check", "run_command"}:
                self.state.last_verification = VerificationResult(
                    step_id=step_id or "verification",
                    success=bool(tool_result.success),
                    summary=str(tool_result.output),
                    command=str(tool_result.meta.get("command") or tool_result.meta.get("must_contain") or ""),
                )
            if not tool_result.success:
                self.state.last_error = str(tool_result.output)
                if step_id is not None:
                    self.state.retry_counts[step_id] = self.state.retry_counts.get(step_id, 0) + 1
                    self._set_step_status(step_id, "failed", note=str(tool_result.output))
            elif step_id is not None:
                self._set_step_status(step_id, "completed", note=str(tool_result.output))
        elif step.action.kind == "final":
            if step_id is not None:
                self._set_step_status(step_id, "completed", note=step.action.final_output or step.action.message)

        task.context.update(self.attach_to_context(task.context))
        self.store.save(self.state)

    def on_finish(self, run: AgentRun) -> None:
        self.state.status = str(run.status)
        self.state.escalations = run.escalations
        self.state.final_output = run.final_output
        self.state.step_count = len(run.steps)
        policy_note = str(run.task.context.get("_programming_policy_note") or "").strip()
        if policy_note:
            self.state.last_policy_decision = policy_note
        run.task.context.update(self.attach_to_context(run.task.context))
        self.store.save(self.state)
