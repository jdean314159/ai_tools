from __future__ import annotations

from pathlib import Path
from shutil import which
import json
import os

import pytest

from diagnostics_agent import (
    CollectionReadError,
    CollectedLogs,
    DiagnosticsOrchestrator,
    LogInterpreter,
    LogTriage,
    ReadOnlySandbox,
    SandboxConfig,
    SandboxResult,
)
from diagnostics_agent.interpret import Interpretation
from diagnostics_agent.system_facts import SystemFacts
from llm_engines.contracts import ChatMessage, GenerationRequest, GenerationResponse, UsageStats


def test_full_chain_without_sandbox_returns_summary_interpretation_and_audit() -> None:
    collector = _FakeCollector(_sample_log())
    interpreter = LogInterpreter(_StubEngine(_valid_interpretation_json()))
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=LogTriage(),
        interpreter=interpreter,
        sandbox=None,
    )

    result = orchestrator.run()

    assert result.sandbox_result is None
    assert result.summary.total_lines == 2
    assert result.interpretation is not None
    assert result.interpretation.summary == "Authentication warning detected."
    assert result.interpretation_error is None
    assert result.audit["collection"]["command"] == ["fake-collect"]
    assert result.audit["read"]["sandbox_enabled"] is False
    assert result.audit["system_facts"] is not None
    json.dumps(result.audit)
    json.dumps(result.to_dict())


def test_interpretation_failure_preserves_summary_and_audit() -> None:
    collector = _FakeCollector(_sample_log())
    interpreter = LogInterpreter(_StubEngine("not json"))
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=LogTriage(),
        interpreter=interpreter,
        sandbox=None,
    )

    result = orchestrator.run()

    assert result.summary.total_lines == 2
    assert result.interpretation is None
    assert result.interpretation_error is not None
    assert "not valid Interpretation JSON" in result.interpretation_error
    assert result.audit["summary"]["total_lines"] == 2
    assert result.audit["interpretation"] is None
    json.dumps(result.audit)


def test_remote_refusal_occurs_when_interpreter_is_constructed() -> None:
    with pytest.raises(Exception) as exc_info:
        LogInterpreter(_StubEngine(_valid_interpretation_json(), backend="openai"))

    assert "refusing unapproved backend" in str(exc_info.value)


def test_staging_dir_is_removed_after_normal_run() -> None:
    collector = _FakeCollector(_sample_log())
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=LogTriage(),
        interpreter=LogInterpreter(_StubEngine(_valid_interpretation_json())),
        sandbox=None,
    )

    orchestrator.run()

    assert collector.staging_dir is not None
    assert not collector.staging_dir.exists()


def test_staging_dir_is_removed_after_error() -> None:
    collector = _FailingCollector()
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=LogTriage(),
        interpreter=LogInterpreter(_StubEngine(_valid_interpretation_json())),
        sandbox=None,
    )

    with pytest.raises(RuntimeError, match="collection failed"):
        orchestrator.run()

    assert collector.staging_dir is not None
    assert not collector.staging_dir.exists()


def test_sandbox_read_failure_aborts_before_triage() -> None:
    collector = _FakeCollector(_sample_log())
    triage = _TriageShouldNotRun()
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=triage,  # type: ignore[arg-type]
        interpreter=LogInterpreter(_StubEngine(_valid_interpretation_json())),
        sandbox=_FailingSandbox(),
    )

    with pytest.raises(CollectionReadError, match="sandbox read failed"):
        orchestrator.run()

    assert triage.called is False
    assert collector.staging_dir is not None
    assert not collector.staging_dir.exists()


def test_system_facts_are_passed_to_interpreter_and_audit(monkeypatch) -> None:
    facts = SystemFacts(
        hostname="hammerhead",
        kernel_release="6.17.0-23-generic",
        kernel_version="#1 SMP",
        os_name="Ubuntu 25.10",
        os_version="25.10",
        arch="x86_64",
    )
    collector = _FakeCollector(_sample_log())
    interpreter = _CapturingInterpreter()
    monkeypatch.setattr(
        "diagnostics_agent.orchestrate.collect_system_facts",
        lambda: facts,
    )
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=LogTriage(),
        interpreter=interpreter,  # type: ignore[arg-type]
        sandbox=None,
    )

    result = orchestrator.run()

    assert interpreter.system_facts == facts
    assert result.audit["system_facts"] == facts.to_dict()
    assert result.interpretation is not None


def test_system_fact_collection_failure_is_non_fatal(monkeypatch) -> None:
    collector = _FakeCollector(_sample_log())
    interpreter = _CapturingInterpreter()

    def fail() -> SystemFacts:
        raise OSError("cannot read facts")

    monkeypatch.setattr("diagnostics_agent.orchestrate.collect_system_facts", fail)
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=LogTriage(),
        interpreter=interpreter,  # type: ignore[arg-type]
        sandbox=None,
    )

    result = orchestrator.run()

    assert interpreter.system_facts is None
    assert result.audit["system_facts"] is None
    assert result.interpretation is not None


@pytest.mark.skipif(which("podman") is None, reason="podman is not installed")
def test_sandbox_read_path_flows_to_triage() -> None:
    collector = _FakeCollector(_sample_log())
    sandbox = ReadOnlySandbox(
        SandboxConfig(
            user=f"{os.getuid()}:{os.getgid()}",
            extra_run_args=("--userns=keep-id",),
        )
    )
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=LogTriage(),
        interpreter=LogInterpreter(_StubEngine(_valid_interpretation_json())),
        sandbox=sandbox,
    )

    result = orchestrator.run()

    assert result.sandbox_result is not None
    assert result.sandbox_result.exit_code == 0
    assert result.sandbox_result.stdout == _sample_log()
    assert result.summary.total_lines == 2
    assert result.audit["read"]["sandbox_enabled"] is True
    assert "--userns=keep-id" in result.sandbox_result.argv


@pytest.mark.skipif(which("podman") is None, reason="podman is not installed")
@pytest.mark.skipif(
    os.environ.get("DIAGNOSTICS_AGENT_LIVE_MODEL") is None,
    reason="DIAGNOSTICS_AGENT_LIVE_MODEL is not set",
)
def test_end_to_end_with_real_sandbox_and_local_model() -> None:
    from llm_engines.backends.ollama import OllamaEngine

    model = os.environ["DIAGNOSTICS_AGENT_LIVE_MODEL"]
    collector = _FakeCollector(_sample_log())
    sandbox = ReadOnlySandbox(
        SandboxConfig(
            user=f"{os.getuid()}:{os.getgid()}",
            extra_run_args=("--userns=keep-id",),
        )
    )
    orchestrator = DiagnosticsOrchestrator(
        collector=collector,
        triage=LogTriage(),
        interpreter=LogInterpreter(OllamaEngine(model=model), temperature=0.0, max_tokens=512),
        sandbox=sandbox,
    )

    result = orchestrator.run()

    assert result.sandbox_result is not None
    assert result.sandbox_result.exit_code == 0
    assert result.interpretation is not None
    assert result.interpretation.reasoning
    assert result.interpretation.summary
    assert result.interpretation.security_risk in {"none", "low", "medium", "high", "critical"}
    assert result.interpretation.operational_risk in {"none", "low", "medium", "high", "critical"}
    assert isinstance(result.interpretation.prioritized_concerns, list)
    assert isinstance(result.interpretation.recommended_checks, list)


def _sample_log() -> str:
    return (
        "2026-05-29T14:03:11-07:00 host sshd[1234]: "
        "Failed password for invalid user admin from 192.0.2.10 port 53001 ssh2\n"
        "2026-05-29T14:04:11-07:00 host app[2222]: "
        "warning connection reset from 198.51.100.10:443\n"
    )


def _valid_interpretation_json() -> str:
    return json.dumps(
        {
            "reasoning": "There is one auth finding and one warning cluster.",
            "summary": "Authentication warning detected.",
            "security_risk": "medium",
            "operational_risk": "low",
            "prioritized_concerns": [
                {
                    "finding_ref": "ssh_failed_auth",
                    "rationale": "Failed authentication should be reviewed.",
                    "severity": "medium",
                }
            ],
            "recommended_checks": ["Review recent auth failures by source IP."],
        }
    )


class _FakeCollector:
    def __init__(self, content: str) -> None:
        self.content = content
        self.staging_dir: Path | None = None

    def collect(self, staging_dir: Path) -> CollectedLogs:
        self.staging_dir = staging_dir
        staging_path = staging_dir / "fixture.log"
        staging_path.write_text(self.content, encoding="utf-8")
        staging_path.chmod(0o600)
        return CollectedLogs(
            staging_path=staging_path,
            command=["fake-collect"],
            source_description="fixture log",
            byte_count=len(self.content.encode("utf-8")),
        )


class _FailingCollector:
    def __init__(self) -> None:
        self.staging_dir: Path | None = None

    def collect(self, staging_dir: Path) -> CollectedLogs:
        self.staging_dir = staging_dir
        raise RuntimeError("collection failed")


class _FailingSandbox:
    config = SandboxConfig()

    def run(self, command: list[str]) -> SandboxResult:
        return SandboxResult(
            argv=["podman", "run", "fake"],
            inner_command=list(command),
            stdout="",
            stderr="cat: can't open '/staging/fixture.log': Permission denied",
            exit_code=1,
            duration_s=0.01,
            timed_out=False,
            truncated=False,
        )


class _TriageShouldNotRun:
    def __init__(self) -> None:
        self.called = False

    def triage(self, source: str):
        self.called = True
        raise AssertionError("triage should not run after a sandbox read failure")


class _CapturingInterpreter:
    def __init__(self) -> None:
        self.system_facts: SystemFacts | None | object = object()

    def interpret(self, summary, *, system_facts=None) -> Interpretation:
        self.system_facts = system_facts
        return Interpretation.model_validate(
            {
                "reasoning": "x",
                "summary": f"{summary.total_lines} lines reviewed.",
                "security_risk": "low",
                "operational_risk": "low",
                "prioritized_concerns": [],
                "recommended_checks": ["Review logs."],
            }
        )


class _StubEngine:
    def __init__(self, content: str, *, backend: str = "ollama") -> None:
        self.backend = backend
        self.content = content

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=self.content),
            finish_reason="stop",
            usage=UsageStats(input_tokens=10, output_tokens=20, total_tokens=30),
            model_name="stub",
            backend=self.backend,
        )
