from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
from typing import Protocol

from diagnostics_agent.collect import CollectedLogs, Collector
from diagnostics_agent.errors import CollectionReadError, InterpreterError
from diagnostics_agent.interpret import Interpretation, LogInterpreter
from diagnostics_agent.sandbox import ReadOnlySandbox, SandboxConfig, SandboxResult
from diagnostics_agent.system_facts import SystemFacts, collect_system_facts
from diagnostics_agent.triage import LogTriage, TriageSummary


class Sandbox(Protocol):
    config: SandboxConfig

    def run(self, command: list[str]) -> SandboxResult: ...


@dataclass(frozen=True)
class DiagnosticResult:
    collected: CollectedLogs
    sandbox_result: SandboxResult | None
    summary: TriageSummary
    interpretation: Interpretation | None
    interpretation_error: str | None
    audit: dict

    def to_dict(self) -> dict:
        return {
            "collected": self.collected.to_dict(),
            "sandbox_result": _sandbox_result_to_dict(self.sandbox_result),
            "summary": self.summary.to_dict(),
            "interpretation": (
                self.interpretation.model_dump(mode="json")
                if self.interpretation is not None
                else None
            ),
            "interpretation_error": self.interpretation_error,
            "audit": self.audit,
        }


class DiagnosticsOrchestrator:
    def __init__(
        self,
        *,
        collector: Collector,
        triage: LogTriage,
        interpreter: LogInterpreter,
        sandbox: Sandbox | None = None,
        sandbox_factory: Callable[[SandboxConfig], Sandbox] = ReadOnlySandbox,
        sandbox_mount: str = "/staging",
        read_command: list[str] | None = None,
    ) -> None:
        self.collector = collector
        self.triage = triage
        self.interpreter = interpreter
        self.sandbox = sandbox
        self.sandbox_factory = sandbox_factory
        self.sandbox_mount = sandbox_mount
        self.read_command = list(read_command) if read_command is not None else None

    def run(self) -> DiagnosticResult:
        run_started = _utc_now_iso()
        staging_dir = Path(tempfile.mkdtemp(prefix="diagnostics-agent-"))
        staging_dir.chmod(0o700)
        try:
            collected = self.collector.collect(staging_dir)
            text, sandbox_result, read_command = self._read_collected_logs(
                staging_dir=staging_dir,
                collected=collected,
            )
            summary = self.triage.triage(text)
            system_facts = self._collect_system_facts()
            interpretation, interpretation_error = self._interpret(
                summary,
                system_facts=system_facts,
            )
            audit = self._build_audit(
                run_started=run_started,
                collected=collected,
                sandbox_result=sandbox_result,
                read_command=read_command,
                summary=summary,
                system_facts=system_facts,
                interpretation=interpretation,
                interpretation_error=interpretation_error,
            )
            return DiagnosticResult(
                collected=collected,
                sandbox_result=sandbox_result,
                summary=summary,
                interpretation=interpretation,
                interpretation_error=interpretation_error,
                audit=audit,
            )
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    def _read_collected_logs(
        self,
        *,
        staging_dir: Path,
        collected: CollectedLogs,
    ) -> tuple[str, SandboxResult | None, list[str]]:
        if self.sandbox is None:
            return collected.staging_path.read_text(encoding="utf-8"), None, []

        read_command = self.read_command or [
            "cat",
            f"{self.sandbox_mount}/{collected.staging_path.name}",
        ]
        sandbox = self._sandbox_with_staging_mount(staging_dir)
        sandbox_result = sandbox.run(read_command)
        if sandbox_result.timed_out or sandbox_result.exit_code != 0:
            stderr = sandbox_result.stderr.strip()
            raise CollectionReadError(
                f"sandbox read failed (exit {sandbox_result.exit_code}, "
                f"timed_out={sandbox_result.timed_out}): {stderr}. "
                "If this is a permission error, the sandbox user must be able to read "
                "the 0600 staged file; configure user={uid}:{gid} with --userns=keep-id."
            )
        return sandbox_result.stdout, sandbox_result, read_command

    def _sandbox_with_staging_mount(self, staging_dir: Path) -> Sandbox:
        assert self.sandbox is not None
        config = self.sandbox.config
        mounts = tuple(config.mounts) + ((str(staging_dir), self.sandbox_mount),)
        return self.sandbox_factory(replace(config, mounts=mounts))

    def _collect_system_facts(self) -> SystemFacts | None:
        try:
            return collect_system_facts()
        except Exception:
            return None

    def _interpret(
        self,
        summary: TriageSummary,
        *,
        system_facts: SystemFacts | None,
    ) -> tuple[Interpretation | None, str | None]:
        try:
            return self.interpreter.interpret(summary, system_facts=system_facts), None
        except InterpreterError as exc:
            return None, str(exc)

    def _build_audit(
        self,
        *,
        run_started: str,
        collected: CollectedLogs,
        sandbox_result: SandboxResult | None,
        read_command: list[str],
        summary: TriageSummary,
        system_facts: SystemFacts | None,
        interpretation: Interpretation | None,
        interpretation_error: str | None,
    ) -> dict:
        return {
            "run_started": run_started,
            "run_finished": _utc_now_iso(),
            "collection": collected.to_dict(),
            "read": {
                "sandbox_enabled": sandbox_result is not None,
                "command": list(read_command),
                "sandbox": _sandbox_result_to_dict(sandbox_result),
            },
            "summary": summary.to_dict(),
            "system_facts": system_facts.to_dict() if system_facts is not None else None,
            "interpretation": (
                interpretation.model_dump(mode="json") if interpretation is not None else None
            ),
            "interpretation_error": interpretation_error,
        }


def _sandbox_result_to_dict(result: SandboxResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "argv": list(result.argv),
        "inner_command": list(result.inner_command),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "duration_s": result.duration_s,
        "timed_out": result.timed_out,
        "truncated": result.truncated,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
