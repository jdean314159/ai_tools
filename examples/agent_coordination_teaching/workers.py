from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    kind: str
    model: str | None = None
    backend: str | None = None
    base_url: str | None = None
    is_cloud: bool | None = None
    n_gpu_layers: int | None = None
    n_ctx: int | None = None
    n_threads: int | None = None
    command: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerResult:
    worker: str
    success: bool
    output: str
    returncode: int = 0
    command: tuple[str, ...] = ()


class WorkerAdapter(Protocol):
    spec: WorkerSpec

    def available(self) -> bool: ...
    def launch(self, *, workspace: Path, prompt: str, timeout_seconds: int) -> WorkerResult: ...


class MockWorkerAdapter:
    def __init__(self, spec: WorkerSpec) -> None:
        self.spec = spec

    def available(self) -> bool:
        return True

    def launch(self, *, workspace: Path, prompt: str, timeout_seconds: int) -> WorkerResult:
        assignment_file = workspace / f"{self.spec.name}_assignment.txt"
        assignment_file.write_text(prompt, encoding="utf-8")
        return WorkerResult(
            worker=self.spec.name,
            success=True,
            output=f"{self.spec.name} accepted the assignment and wrote {assignment_file.name}.",
            command=("mock-worker", self.spec.name),
        )


class CodexExecWorkerAdapter:
    def __init__(self, spec: WorkerSpec) -> None:
        self.spec = spec

    def available(self) -> bool:
        return shutil.which("codex") is not None

    def launch(self, *, workspace: Path, prompt: str, timeout_seconds: int) -> WorkerResult:
        command = [
            "codex",
            "exec",
            "--cd",
            str(workspace),
            "--sandbox",
            "workspace-write",
            "--ask-for-approval",
            "on-request",
        ]
        if self.spec.model:
            command.extend(["--model", self.spec.model])
        command.append("-")
        return _run_command(
            command, prompt=prompt, timeout_seconds=timeout_seconds, worker=self.spec.name
        )


class ClaudePrintWorkerAdapter:
    """Configurable Claude Code one-shot adapter.

    Claude Code installations vary. The default uses a common print-mode shape,
    but callers can provide an explicit command tuple in WorkerSpec.command.

    Isolation note (ADR-011): unlike the Codex adapter, which uses
    ``codex exec --sandbox workspace-write --ask-for-approval on-request``,
    this adapter does not add Claude-side sandboxing flags because the surface
    varies across installations. For non-toy use, wrap the runner in a
    container with the workspace bind-mounted read/write and ``--network none``
    (see ADR-011 for the recommended baseline).
    """

    def __init__(self, spec: WorkerSpec) -> None:
        self.spec = spec

    def available(self) -> bool:
        command = self.spec.command[0] if self.spec.command else "claude"
        return shutil.which(command) is not None

    def launch(self, *, workspace: Path, prompt: str, timeout_seconds: int) -> WorkerResult:
        command = list(self.spec.command or ("claude", "--print"))
        if "--cwd" not in command and "--cd" not in command:
            command.extend(["--cwd", str(workspace)])
        return _run_command(
            command, prompt=prompt, timeout_seconds=timeout_seconds, worker=self.spec.name
        )


class LLMEngineWorkerAdapter:
    """ai_tools-native worker backed by llm_engines."""

    def __init__(self, spec: WorkerSpec) -> None:
        self.spec = spec

    def available(self) -> bool:
        try:
            self._build_engine()
        except Exception:
            return False
        return True

    def launch(self, *, workspace: Path, prompt: str, timeout_seconds: int) -> WorkerResult:
        # NOTE on isolation (ADR-011): this adapter runs the model in-process
        # and has no filesystem/process/network boundary. To keep that honest,
        # the worker is *text-only* — it produces a response describing what it
        # would do, and does not write into the workspace. For real coding-agent
        # work, prefer the Codex or Claude Code adapters (which bring their own
        # sandboxing) under a container-isolated runner.
        try:
            engine = self._build_engine()
            from llm_engines import ChatMessage, GenerationRequest

            response = engine.generate(
                GenerationRequest(
                    messages=[
                        ChatMessage(
                            role="system",
                            content=(
                                "You are an ai_tools-native worker in a teaching demo. "
                                "You CANNOT edit files; describe in plain text what you would do. "
                                "Stay concise and reference the provided workspace path only as context."
                            ),
                        ),
                        ChatMessage(role="user", content=prompt),
                    ],
                    max_tokens=500,
                    temperature=0.2,
                )
            )
        except Exception as exc:
            return WorkerResult(
                worker=self.spec.name,
                success=False,
                output=f"llm_engines worker failed: {exc}",
                returncode=1,
                command=self._describe_command(),
            )

        # Text-only: do not write into the workspace. The response is returned
        # as the WorkerResult.output and persisted by the exchange log only.
        return WorkerResult(
            worker=self.spec.name,
            success=True,
            output=response.text,
            command=self._describe_command(),
        )

    def _build_engine(self):
        backend = self.spec.backend or "ollama"
        model = self.spec.model
        if backend in {"llamacpp", "llama_cpp"}:
            if not model:
                raise ValueError(
                    "llm_engine worker with backend=llamacpp requires --worker-model /path/to/model.gguf"
                )
            from llm_engines import get_engine

            kwargs = {"n_gpu_layers": self.spec.n_gpu_layers or 0}
            if self.spec.n_ctx is not None:
                kwargs["n_ctx"] = self.spec.n_ctx
            if self.spec.n_threads is not None:
                kwargs["n_threads"] = self.spec.n_threads
            return get_engine("llamacpp", model, **kwargs)

        from llm_engines import get_engine

        kwargs = {}
        if self.spec.base_url:
            kwargs["base_url"] = self.spec.base_url
        if self.spec.is_cloud is not None:
            kwargs["is_cloud"] = self.spec.is_cloud
        return get_engine(backend, model or "qwen3:8b", **kwargs)

    def _describe_command(self) -> tuple[str, ...]:
        backend = self.spec.backend or "ollama"
        model = self.spec.model or "qwen3:8b"
        parts = ["llm_engines", backend, model]
        if backend in {"llamacpp", "llama_cpp"}:
            parts.extend(["n_gpu_layers", str(self.spec.n_gpu_layers or 0)])
        return tuple(parts)


def build_worker(spec: WorkerSpec) -> WorkerAdapter:
    if spec.kind == "mock":
        return MockWorkerAdapter(spec)
    if spec.kind == "codex":
        return CodexExecWorkerAdapter(spec)
    if spec.kind == "claude_code":
        return ClaudePrintWorkerAdapter(spec)
    if spec.kind == "llm_engine":
        return LLMEngineWorkerAdapter(spec)
    raise ValueError(f"Unknown worker kind: {spec.kind}")


def _run_command(
    command: list[str], *, prompt: str, timeout_seconds: int, worker: str
) -> WorkerResult:
    """
    Run a worker subprocess. Confinement-wise this provides only a wall-clock
    timeout. Per ADR-011, that is insufficient for an autonomous worker loop
    — for non-toy use, run the whole demo inside a container with the workspace
    bind-mounted and ``--network none`` (or rootless Podman with the equivalent
    flags). This example treats the host as trusted; the design notes in
    ``docs/design/AGENT_BUILD_NOTES.md`` §4 describe the intended baseline.
    """
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return WorkerResult(
            worker=worker,
            success=False,
            output=f"Timed out after {timeout_seconds}s.\n{exc.stdout or ''}\n{exc.stderr or ''}".strip(),
            returncode=124,
            command=tuple(command),
        )
    except OSError as exc:
        return WorkerResult(
            worker=worker,
            success=False,
            output=f"Could not launch worker: {exc}",
            returncode=1,
            command=tuple(command),
        )

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if not output:
        output = "(no output)"
    return WorkerResult(
        worker=worker,
        success=completed.returncode == 0,
        output=output,
        returncode=completed.returncode,
        command=tuple(command),
    )


def detect_worker_capabilities() -> dict[str, bool]:
    return {
        "mock": True,
        "codex": shutil.which("codex") is not None,
        "claude_code": shutil.which("claude") is not None,
        "llm_engine": True,
        "python": shutil.which(sys.executable) is not None,
    }
