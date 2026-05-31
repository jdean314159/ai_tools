from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from shutil import which
import subprocess
import time
from collections.abc import Sequence
from uuid import uuid4

from diagnostics_agent.errors import ImageNotAvailableError, MountError, RuntimeNotFoundError


@dataclass(frozen=True)
class SandboxConfig:
    image: str = "docker.io/library/alpine:3.20"
    mounts: tuple[tuple[str, str], ...] = ()
    memory: str = "256m"
    cpus: str = "1.0"
    pids_limit: int = 128
    timeout_s: float = 30.0
    max_output_bytes: int = 1_048_576
    user: str = "65534:65534"
    tmpfs_tmp: bool = True
    tmpfs_size: str = "16m"
    runtime: str = "podman"
    extra_run_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxResult:
    argv: list[str]
    inner_command: list[str]
    stdout: str
    stderr: str
    exit_code: int
    duration_s: float
    timed_out: bool
    truncated: bool


class ReadOnlySandbox:
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    def build_argv(self, command: Sequence[str]) -> list[str]:
        """Construct the container-runtime argv without running subprocesses."""
        inner_command = list(command)
        if not inner_command:
            raise ValueError("command must not be empty")

        self._validate_mount_shapes()

        name = f"diag-sbx-{uuid4().hex}"
        argv = [
            self.config.runtime,
            "run",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            self.config.user,
            "--pids-limit",
            str(self.config.pids_limit),
            "--memory",
            self.config.memory,
            "--cpus",
            self.config.cpus,
            "--rm",
            "--name",
            name,
        ]

        for host_path, container_path in self.config.mounts:
            argv.extend(["-v", f"{host_path}:{container_path}:ro"])

        if self.config.tmpfs_tmp:
            argv.extend(["--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={self.config.tmpfs_size}"])

        _validate_extra_run_args(self.config.extra_run_args)
        argv.extend(self.config.extra_run_args)
        argv.append(self.config.image)
        argv.extend(inner_command)
        return argv

    def preflight(self) -> None:
        runtime_path = which(self.config.runtime)
        if runtime_path is None:
            raise RuntimeNotFoundError(f"container runtime not found: {self.config.runtime}")

        self._validate_mount_shapes()
        for host_path, _container_path in self.config.mounts:
            if not Path(host_path).exists():
                raise MountError(f"mount host path does not exist: {host_path}")

        image_check = subprocess.run(
            [self.config.runtime, "image", "inspect", self.config.image],
            capture_output=True,
            text=True,
            check=False,
        )
        if image_check.returncode != 0:
            raise ImageNotAvailableError(f"container image is not available locally: {self.config.image}")

    def run(self, command: Sequence[str]) -> SandboxResult:
        self.preflight()
        inner_command = list(command)
        argv = self.build_argv(inner_command)
        name = _container_name_from_argv(argv)

        started = time.monotonic()
        completed: subprocess.CompletedProcess[str] | None = None
        timed_out = False
        exit_code = 0
        stdout = ""
        stderr = ""

        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_s,
                check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = 124
            stdout = _coerce_output(exc.stdout)
            stderr = _coerce_output(exc.stderr)
        finally:
            duration_s = time.monotonic() - started
            subprocess.run(
                [self.config.runtime, "rm", "-f", name],
                capture_output=True,
                text=True,
                check=False,
            )

        stdout, stdout_truncated = _truncate_text(stdout, self.config.max_output_bytes)
        stderr, stderr_truncated = _truncate_text(stderr, self.config.max_output_bytes)

        return SandboxResult(
            argv=argv,
            inner_command=inner_command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_s=duration_s,
            timed_out=timed_out,
            truncated=stdout_truncated or stderr_truncated,
        )

    def _validate_mount_shapes(self) -> None:
        for host_path, container_path in self.config.mounts:
            if not Path(host_path).is_absolute():
                raise MountError(f"mount host path must be absolute: {host_path}")
            if not container_path.startswith("/"):
                raise MountError(f"mount container path must be absolute: {container_path}")


def make_staging_sandbox(*, image: str = "docker.io/library/alpine:3.20") -> ReadOnlySandbox:
    return ReadOnlySandbox(
        SandboxConfig(
            image=image,
            user=f"{os.getuid()}:{os.getgid()}",
            extra_run_args=("--userns=keep-id",),
        )
    )


def _container_name_from_argv(argv: Sequence[str]) -> str:
    try:
        name_index = argv.index("--name")
    except ValueError as exc:
        raise RuntimeError("sandbox argv is missing --name") from exc

    try:
        return argv[name_index + 1]
    except IndexError as exc:
        raise RuntimeError("sandbox argv has --name without a value") from exc


def _validate_extra_run_args(extra_run_args: Sequence[str]) -> None:
    forbidden_exact = {"--privileged", "--cap-add", "--device", "-v", "--volume", "--mount"}
    forbidden_prefixes = (
        "--privileged=",
        "--cap-add=",
        "--device=",
        "--volume=",
        "--mount=",
    )

    for index, arg in enumerate(extra_run_args):
        if arg in forbidden_exact or arg.startswith(forbidden_prefixes):
            raise ValueError(f"extra_run_args cannot include unsafe runtime flag: {arg}")
        if arg == "--network":
            value = extra_run_args[index + 1] if index + 1 < len(extra_run_args) else ""
            if value != "none":
                raise ValueError("extra_run_args cannot set --network to any value except none")
        if arg.startswith("--network=") and arg != "--network=none":
            raise ValueError("extra_run_args cannot set --network to any value except none")


def _coerce_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _truncate_text(text: str, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True
