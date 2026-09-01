from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
from typing import Any, Literal, Sequence

try:  # Multi-process lease state is supported on POSIX workstations.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on unsupported platforms.
    fcntl = None  # type: ignore[assignment]


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
    # None preserves the historic unrestricted behavior; [] denies every tool.
    allowed_tools: list[str] | None = None
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
    allowed_environment_keys: list[str] = field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ENVIRONMENT_KEYS)
    )
    denied_environment_keys: list[str] = field(default_factory=list)
    command_isolation_backend: SandboxBackend = "host"
    command_isolation_image: str = "python:3.12-slim"
    command_isolation_network: bool = False
    command_isolation_fallback_to_host: bool = False
    command_isolation_extra_args: list[str] = field(default_factory=list)
    command_isolation_mount_path: str = "/workspace"


def _normalize_rel_path(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    normalized = os.path.normpath(raw).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized == ".":
        return ""
    return normalized


def _path_matches_allowlist(path: str, allowed: Sequence[str]) -> bool:
    normalized = _normalize_rel_path(path)
    if not normalized:
        return False
    for raw in allowed:
        candidate = _normalize_rel_path(str(raw or ""))
        if not candidate:
            continue
        if normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


def _command_allowed(command: str, allowed: Sequence[str]) -> bool:
    normalized = (
        " ".join(shlex.split(str(command or "").strip())) if str(command or "").strip() else ""
    )
    if not normalized:
        return False
    allowed_norm = []
    for item in allowed:
        raw = str(item or "").strip()
        if not raw:
            continue
        allowed_norm.append(" ".join(shlex.split(raw)))
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
    value = str(text or "")
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
    requested = str(getattr(policy, "command_isolation_backend", "host") or "host").strip().lower()
    if not requested:
        requested = "host"
    result: dict[str, Any] = {
        "requested_backend": requested,
        "backend": "host",
        "external": False,
        "fallback_used": False,
        "engine_path": None,
        "error": None,
        "available_backends": [name for name in ("docker", "podman") if shutil.which(name)],
    }
    if requested == "host":
        return result
    candidates = []
    if requested == "auto":
        candidates = ["docker", "podman"]
    elif requested in {"docker", "podman"}:
        candidates = [requested]
    else:
        result["error"] = "invalid_sandbox_backend"
        return result
    for candidate in candidates:
        engine_path = shutil.which(candidate)
        if engine_path:
            result.update({"backend": candidate, "external": True, "engine_path": engine_path})
            return result
    if bool(getattr(policy, "command_isolation_fallback_to_host", False)):
        result["fallback_used"] = True
        return result
    result["error"] = "sandbox_unavailable"
    return result


def _build_container_command(
    *,
    workspace: Path,
    command: str,
    policy: WorkspacePolicy,
    backend: str,
    env: dict[str, str],
) -> list[str]:
    mount_path = (
        str(getattr(policy, "command_isolation_mount_path", "/workspace") or "/workspace").strip()
        or "/workspace"
    )
    image = (
        str(
            getattr(policy, "command_isolation_image", "python:3.12-slim") or "python:3.12-slim"
        ).strip()
        or "python:3.12-slim"
    )
    argv: list[str] = [
        backend,
        "run",
        "--rm",
        "--workdir",
        mount_path,
        "--volume",
        f"{workspace}:{mount_path}",
    ]
    if not bool(getattr(policy, "command_isolation_network", False)):
        argv.extend(["--network", "none"])
    if os.name == "posix" and hasattr(os, "getuid") and hasattr(os, "getgid"):
        argv.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    for key, value in env.items():
        argv.extend(["-e", f"{key}={value}"])
    for item in list(getattr(policy, "command_isolation_extra_args", []) or []):
        raw = str(item or "").strip()
        if raw:
            argv.append(raw)
    argv.append(image)
    argv.extend(["/bin/sh", "-lc", command])
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
    released_paths: list[str] = field(default_factory=list)


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
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @contextmanager
    def _lease_lock(self, *, timeout_seconds: float = 5.0):
        """Serialize lease mutations across processes sharing this state root."""
        if fcntl is None:
            raise RuntimeError("Patch lease coordination requires POSIX fcntl support.")
        lock_path = self._leases_path.with_suffix(".lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + timeout_seconds
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Timed out acquiring patch lease lock {lock_path}.")
                    time.sleep(0.01)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _is_git_repo(self, root: Path) -> bool:
        if shutil.which("git") is None:
            return False
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def _prepare_git_worktree(
        self,
        base_root: Path,
        owner_id: str,
        policy: WorkspacePolicy,
        target: Path,
        *,
        mode: IsolationMode,
    ) -> WorkspaceAllocation | None:
        if mode not in {"branch", "worktree"} or not self._is_git_repo(base_root):
            return None
        branch_name = f"{policy.branch_prefix}{self._safe_owner(owner_id)}"
        if not target.exists():
            proc = subprocess.run(
                [
                    "git",
                    "-C",
                    str(base_root),
                    "worktree",
                    "add",
                    "--force",
                    "-B",
                    branch_name,
                    str(target),
                    "HEAD",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                return None
        return WorkspaceAllocation(
            owner_id=owner_id,
            root=str(target),
            isolation_mode=mode,
            source="git_worktree",
            branch_name=branch_name,
        )

    def _prepare_copy_workspace(
        self, base_root: Path, owner_id: str, target: Path, *, mode: IsolationMode
    ) -> WorkspaceAllocation:
        if not target.exists():
            ignore_names = {self.state_root.name, "__pycache__", ".pytest_cache"}
            shutil.copytree(base_root, target, ignore=shutil.ignore_patterns(*ignore_names))
        return WorkspaceAllocation(
            owner_id=owner_id, root=str(target), isolation_mode=mode, source="copy"
        )

    def prepare_workspace(
        self, base_root: str | Path, owner_id: str, policy: WorkspacePolicy
    ) -> WorkspaceAllocation:
        base = Path(base_root).expanduser().resolve()
        mode = policy.isolation_mode
        if mode == "in_place":
            allocation = WorkspaceAllocation(
                owner_id=owner_id, root=str(base), isolation_mode=mode, source="in_place"
            )
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

    def acquire_patch_lease(
        self,
        owner_id: str,
        paths: Sequence[str],
        *,
        thread_id: str = "default",
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PatchOwnership:
        normalized = [_normalize_rel_path(path) for path in paths if _normalize_rel_path(path)]
        with self._lease_lock():
            leases = self.active_patch_owners()
            for path in normalized:
                existing = dict(leases.get(path) or {})
                if (
                    existing
                    and existing.get("status") == "active"
                    and existing.get("owner_id") != owner_id
                ):
                    return PatchOwnership(
                        owner_id=owner_id,
                        paths=normalized,
                        status="denied",
                        reason=f"{path} is currently owned by {existing.get('owner_id')}",
                    )
            now = datetime.now(timezone.utc).isoformat()
            for path in normalized:
                existing = dict(leases.get(path) or {})
                if existing.get("status") == "active" and existing.get("owner_id") == owner_id:
                    # Preserve existing scope; only fill fields absent from a legacy record.
                    existing.setdefault("thread_id", thread_id)
                    existing.setdefault("note", note)
                    existing.setdefault("created_at", now)
                    existing.setdefault("metadata", dict(metadata or {}))
                    leases[path] = existing
                    continue
                leases[path] = {
                    "owner_id": owner_id,
                    "status": "active",
                    "thread_id": thread_id,
                    "note": note,
                    "created_at": now,
                    "metadata": dict(metadata or {}),
                }
            self._save_json(self._leases_path, leases)
        return PatchOwnership(owner_id=owner_id, paths=normalized, status="active")

    def release_patch_lease(self, owner_id: str, paths: Sequence[str]) -> PatchOwnership:
        normalized = [_normalize_rel_path(path) for path in paths if _normalize_rel_path(path)]
        released_paths: list[str] = []
        with self._lease_lock():
            leases = self.active_patch_owners()
            for path in normalized:
                existing = dict(leases.get(path) or {})
                if existing.get("owner_id") == owner_id and existing.get("status") == "active":
                    existing["status"] = "released"
                    existing["released_at"] = datetime.now(timezone.utc).isoformat()
                    leases[path] = existing
                    released_paths.append(path)
            self._save_json(self._leases_path, leases)
        return PatchOwnership(
            owner_id=owner_id, paths=normalized, status="released", released_paths=released_paths
        )

    def patch_lease(self, path: str) -> dict[str, Any] | None:
        record = self.active_patch_owners().get(_normalize_rel_path(path))
        return dict(record) if isinstance(record, dict) else None
