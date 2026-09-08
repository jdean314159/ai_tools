"""Run one frozen baseline or planner repository-assessment condition.

This is experiment-specific tooling, not the production
``repository-assessment/v1`` recorder. See the adjacent preregistration before
changing behavior or running the live campaign.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import time
from typing import Any, Literal, Protocol

from llm_engines.backends.openai import OpenAIEngine
from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    ToolParameterSchema,
    ToolSpec,
)


TARGET_COMMIT = "83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532"
TARGET_ARCHIVE_SHA256 = "e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2"
TURN_BUDGET = 45
MAX_SCOPE_CALLS = 5
MAX_CRITIC_CALLS = 3
MIN_LOW_UNCERTAINTY_COVERAGE = 8
VALID_SEEDS = {17, 31, 47}
PACKAGE_NAMES = (
    "agent_lib",
    "llm_engines",
    "llm_harness_core",
    "llm_inspector",
    "engram",
    "rag_lib",
    "llm_inspector_ui",
    "action_trajectory_loop_guard",
    "mail_lib",
)

SYSTEM_PROMPT = """You are performing a rigorous, read-only assessment of a Python repository.

Your goal is to identify real, currently actionable defects in correctness, data integrity,
security boundaries, persistence, concurrency, packaging, or public contracts. Prefer a few
high-confidence findings over a long speculative list.

Work empirically:
- inspect the relevant call path end to end;
- distinguish current code from historical documentation;
- run focused tests or non-destructive reproducers when useful;
- actively try to disprove each suspected defect;
- downgrade or discard claims contradicted by evidence;
- do not report style preferences, speculative features, or already-documented limitations as defects.

The shell runs inside an isolated environment. /workspace is the repository root and is read-only.
The sandbox has no network. /tmp is private and writable for test/reproducer scratch data. Do not
attempt to modify source files. Use shell for inspection and tests. Do not use shell to submit the
answer.

When the assessment is complete, call submit_report exactly once. The report must include:
1. an executive verdict;
2. each validated finding with severity, exact file/line or symbol, impact, evidence, and a minimal
   remediation direction;
3. rejected or downgraded hypotheses and why;
4. commands/tests actually run and their outcomes;
5. remaining uncertainty and uninspected areas.

If no new validated defect remains, say so explicitly rather than manufacturing one.
"""

USER_PROMPT = (
    "Assess the repository in /workspace. Begin by reading its agent instructions and "
    "current architecture/status documents, then investigate the implementation."
)

SHELL_TOOL = ToolSpec(
    name="shell",
    description=(
        "Run one non-interactive shell command inside the isolated read-only repository. "
        "The repository is /workspace; /tmp is writable; network is unavailable."
    ),
    parameters={
        "command": ToolParameterSchema(
            type="string",
            description="A non-interactive shell command for inspection, tests, or a /tmp reproducer.",
        )
    },
    required_params=["command"],
)

REPORT_TOOL = ToolSpec(
    name="submit_report",
    description="Submit the final repository assessment as Markdown and end the run.",
    parameters={
        "report": ToolParameterSchema(
            type="string",
            description="Complete self-contained Markdown assessment report.",
        ),
        "remaining_uncertainty": ToolParameterSchema(
            type="string",
            enum=["low", "medium", "high"],
            description="Overall uncertainty after accounting for uninspected repository areas.",
        ),
    },
    required_params=["report", "remaining_uncertainty"],
)

CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["accept", "reject", "insufficient_evidence"],
        },
        "rationale": {"type": "string"},
    },
    "required": ["decision", "rationale"],
    "additionalProperties": False,
}

PATH_RE = re.compile(r"/workspace/[A-Za-z0-9_./-]+")
INSPECTION_RE = re.compile(r"(^|[;&|]\s*)(cat|sed|head|tail|rg|grep|awk)\b")
VALIDATED_HEADING_RE = re.compile(r"(?im)^(#{1,6})\s+Validated Findings?\s*$")
KEY_FINDINGS_HEADING_RE = re.compile(r"(?im)^(#{1,6})\s+Key Findings?\s*$")


class ToolEngine(Protocol):
    def generate_with_tools(
        self, request: GenerationRequest, available_tools: list[ToolSpec]
    ) -> GenerationResponse: ...

    def generate(self, request: GenerationRequest) -> GenerationResponse: ...


@dataclass
class ScopeEvidence:
    shell_calls: int = 0
    exposed: bool = False
    production_reads: set[str] = field(default_factory=set)
    corroborating_reads: set[str] = field(default_factory=set)
    exhausted: bool = False

    @property
    def covered(self) -> bool:
        return bool(self.production_reads and self.corroborating_reads)


@dataclass
class CoverageLedger:
    seed: int
    order: list[str] = field(init=False)
    scopes: dict[str, ScopeEvidence] = field(init=False)
    current_index: int = 0

    def __post_init__(self) -> None:
        self.order = list(PACKAGE_NAMES)
        random.Random(self.seed).shuffle(self.order)
        self.scopes = {name: ScopeEvidence() for name in PACKAGE_NAMES}
        self.scopes[self.order[0]].exposed = True

    @property
    def current_scope(self) -> str | None:
        if self.current_index >= len(self.order):
            return None
        return self.order[self.current_index]

    @property
    def covered_count(self) -> int:
        return sum(scope.covered for scope in self.scopes.values())

    @property
    def exposed_count(self) -> int:
        return sum(scope.exposed for scope in self.scopes.values())

    def command_matches_current_scope(self, command: str) -> bool:
        scope = self.current_scope
        return scope is not None and f"/workspace/{scope}" in command

    def observe(self, command: str, result: dict[str, Any]) -> bool:
        """Record one executed command and return whether the scope advanced."""
        scope_name = self.current_scope
        if scope_name is None:
            return False
        scope = self.scopes[scope_name]
        scope.shell_calls += 1
        if _successful_inspection(command, result):
            for path in _command_paths(command):
                if _is_production_path(scope_name, path):
                    scope.production_reads.add(path)
                if _is_corroborating_path(scope_name, path):
                    scope.corroborating_reads.add(path)

        if not scope.covered and scope.shell_calls < MAX_SCOPE_CALLS:
            return False
        scope.exhausted = not scope.covered
        self.current_index += 1
        if self.current_scope is not None:
            self.scopes[self.current_scope].exposed = True
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "order": list(self.order),
            "current_scope": self.current_scope,
            "covered": self.covered_count,
            "exposed": self.exposed_count,
            "scopes": {
                name: {
                    "shell_calls": value.shell_calls,
                    "exposed": value.exposed,
                    "covered": value.covered,
                    "exhausted": value.exhausted,
                    "production_reads": sorted(value.production_reads),
                    "corroborating_reads": sorted(value.corroborating_reads),
                }
                for name, value in self.scopes.items()
            },
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def _command_paths(command: str) -> set[str]:
    return {match.rstrip("./") for match in PATH_RE.findall(command)}


def _successful_inspection(command: str, result: dict[str, Any]) -> bool:
    return bool(
        INSPECTION_RE.search(command)
        and result.get("returncode") == 0
        and result.get("stdout_length", 0) > 0
    )


def _is_production_path(scope: str, path: str) -> bool:
    if scope == "mail_lib":
        relative = path.removeprefix("/workspace/mail_lib/")
        return relative.endswith(".py") and "/" not in relative
    return path.startswith(f"/workspace/{scope}/src/") and path.endswith(".py")


def _is_corroborating_path(scope: str, path: str) -> bool:
    prefix = f"/workspace/{scope}/"
    if path in {prefix + "README.md", prefix + "pyproject.toml"}:
        return True
    return path.startswith(prefix + "tests/") and path.endswith(".py")


def attributed_scope(command: str) -> str:
    matches = [name for name in PACKAGE_NAMES if f"/workspace/{name}" in command]
    return matches[0] if len(matches) == 1 else "cross_repository"


def observe_passive_coverage(
    scopes: dict[str, ScopeEvidence], command: str, result: dict[str, Any]
) -> None:
    if not _successful_inspection(command, result):
        return
    paths = _command_paths(command)
    for scope_name, scope in scopes.items():
        relevant = {path for path in paths if f"/workspace/{scope_name}" in path}
        if not relevant:
            continue
        scope.exposed = True
        for path in relevant:
            if _is_production_path(scope_name, path):
                scope.production_reads.add(path)
            if _is_corroborating_path(scope_name, path):
                scope.corroborating_reads.add(path)


def passive_coverage_snapshot(scopes: dict[str, ScopeEvidence]) -> dict[str, Any]:
    return {
        "covered": sum(scope.covered for scope in scopes.values()),
        "exposed": sum(scope.exposed for scope in scopes.values()),
        "scopes": {
            name: {
                "covered": scope.covered,
                "exposed": scope.exposed,
                "production_reads": sorted(scope.production_reads),
                "corroborating_reads": sorted(scope.corroborating_reads),
            }
            for name, scope in scopes.items()
        },
    }


def planner_instruction(ledger: CoverageLedger) -> str:
    scope = ledger.current_scope
    if scope is None:
        return (
            "Controller ledger: all package scopes have been processed. Synthesize the evidence, "
            "attempt to disprove retained hypotheses, and submit the report when ready."
        )
    evidence = ledger.scopes[scope]
    return (
        f"Controller assignment: inspect only package scope {scope!r} for now. Shell commands must "
        f"explicitly name /workspace/{scope}. Substantive coverage requires reading at least one "
        "production Python source file and one distinct test, README, or pyproject contract. "
        f"This scope has used {evidence.shell_calls}/{MAX_SCOPE_CALLS} shell calls. The controller "
        "will advance after coverage or five calls. Keep, reject, or defer any hypothesis before "
        "leaving the scope. Do not infer which packages contain grader defects."
    )


def clipped(text: str, limit: int = 24_000) -> tuple[str, bool, int]:
    value = str(text or "")
    length = len(value)
    if length <= limit:
        return value, False, length
    head = 15_000
    tail = limit - head
    return (
        value[:head] + "\n...[output clipped by harness]...\n" + value[-tail:],
        True,
        length,
    )


def sandbox_argv(root: Path, venv: Path, rg_path: Path, command: str) -> list[str]:
    pythonpath = ":".join(
        [
            "/workspace/agent_lib/src",
            "/workspace/llm_engines/src",
            "/workspace/llm_harness_core/src",
            "/workspace/llm_inspector/src",
            "/workspace/engram/src",
            "/workspace/rag_lib/src",
            "/workspace/llm_inspector_ui/src",
            "/workspace/action_trajectory_loop_guard/src",
            "/workspace",
        ]
    )
    return [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--ro-bind",
        str(venv),
        "/venv",
        "--dir",
        "/tools",
        "--ro-bind",
        str(rg_path),
        "/tools/rg",
        "--ro-bind",
        str(root),
        "/workspace",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--setenv",
        "PATH",
        "/venv/bin:/tools:/usr/bin:/bin",
        "--setenv",
        "PYTHONPATH",
        pythonpath,
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--setenv",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "1",
        "--setenv",
        "PYTEST_ADDOPTS",
        "-p no:cacheprovider",
        "--setenv",
        "HOME",
        "/tmp/home",
        "--chdir",
        "/workspace",
        "/bin/bash",
        "--noprofile",
        "--norc",
        "-c",
        command,
    ]


def run_shell(root: Path, venv: Path, rg_path: Path, command: str) -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.Popen(
        sandbox_argv(root, venv, rg_path, command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
    elapsed_ms = (time.perf_counter() - started) * 1000
    stdout_value, stdout_clipped, stdout_length = clipped(stdout)
    stderr_value, stderr_clipped, stderr_length = clipped(stderr)
    return {
        "command": command,
        "returncode": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "elapsed_ms": round(elapsed_ms, 3),
        "stdout": stdout_value,
        "stderr": stderr_value,
        "stdout_clipped": stdout_clipped,
        "stderr_clipped": stderr_clipped,
        "stdout_length": stdout_length,
        "stderr_length": stderr_length,
    }


def validate_sandbox(root: Path, venv: Path, rg_path: Path) -> dict[str, Any]:
    command = """python - <<'PY'
import importlib
import json
from pathlib import Path

packages = [
    "agent_lib",
    "llm_engines",
    "llm_harness_core",
    "llm_inspector",
    "engram",
    "rag_lib",
    "llm_inspector_ui",
    "action_trajectory_loop_guard",
    "mail_lib",
]
origins = {}
for name in packages:
    module = importlib.import_module(name)
    origins[name] = str(Path(module.__file__).resolve())

repo_probe = Path("/workspace/.repository-assessment-write-probe")
repository_read_only = False
try:
    repo_probe.write_text("forbidden", encoding="utf-8")
except OSError:
    repository_read_only = True

tmp_probe = Path("/tmp/repository-assessment-write-probe")
tmp_probe.write_text("ok", encoding="utf-8")
interfaces = [
    line.split(":", 1)[0].strip()
    for line in Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
]
payload = {
    "imports_under_workspace": all(path.startswith("/workspace/") for path in origins.values()),
    "module_origins": origins,
    "network_interfaces": interfaces,
    "network_unshared": set(interfaces) <= {"lo"},
    "private_tmp_writable": tmp_probe.read_text(encoding="utf-8") == "ok",
    "repository_read_only": repository_read_only and not repo_probe.exists(),
}
print(json.dumps(payload, sort_keys=True))
PY"""
    result = run_shell(root, venv, rg_path, command)
    try:
        observations = json.loads(result.get("stdout", ""))
    except (TypeError, json.JSONDecodeError):
        observations = {}
    required = (
        "imports_under_workspace",
        "network_unshared",
        "private_tmp_writable",
        "repository_read_only",
    )
    return {
        "valid": result.get("returncode") == 0
        and all(observations.get(name) is True for name in required),
        "observations": observations,
        "returncode": result.get("returncode"),
        "stderr": result.get("stderr", ""),
    }


def tool_output(result: dict[str, Any]) -> str:
    return json.dumps(result, sort_keys=True, ensure_ascii=False)


def extract_validated_findings(report: str) -> list[str]:
    heading = VALIDATED_HEADING_RE.search(report)
    if heading is None:
        heading = KEY_FINDINGS_HEADING_RE.search(report)
    if heading is None:
        if re.search(
            r"(?i)\b(?:no|none)\s+(?:new\s+)?(?:validated\s+)?(?:defects?|findings?)\b"
            r"|\bnone\s+validated\b",
            report,
        ):
            return []
        return [report.strip()] if report.strip() else []
    heading_level = len(heading.group(1))
    section_start = heading.end()
    next_top = re.search(rf"(?m)^#{{1,{heading_level}}}\s+", report[section_start:])
    section_end = section_start + next_top.start() if next_top else len(report)
    section = report[section_start:section_end].strip()
    if not section or re.match(
        r"(?is)^(none\b|none\s+validated\b|no\s+(?:validated|actual|specific)\b)", section
    ):
        return []
    subheadings = (
        list(re.finditer(rf"(?m)^#{{{heading_level + 1},6}}\s+", section))
        if heading_level < 6
        else []
    )
    if not subheadings:
        return [section]
    findings: list[str] = []
    for index, match in enumerate(subheadings):
        end = subheadings[index + 1].start() if index + 1 < len(subheadings) else len(section)
        findings.append(section[match.start() : end].strip())
    return findings


def run_critic(engine: ToolEngine, finding: str, seed: int) -> tuple[dict[str, str], Any]:
    response = engine.generate(
        GenerationRequest(
            messages=[
                ChatMessage(
                    role="system",
                    content=(
                        "You are an evidence critic. Review only the proposed repository defect and "
                        "evidence supplied below. Do not infer missing repository facts. Accept only "
                        "when the evidence demonstrates the claimed behavior and impact; reject a "
                        "disproved claim; otherwise return insufficient_evidence."
                    ),
                ),
                ChatMessage(role="user", content=finding),
            ],
            max_tokens=512,
            temperature=0,
            thinking=False,
            seed=seed,
            json_schema=CRITIC_SCHEMA,
        )
    )
    try:
        parsed = json.loads(response.text)
        decision = parsed["decision"]
        rationale = parsed["rationale"]
        if decision not in {"accept", "reject", "insufficient_evidence"}:
            raise ValueError("unknown critic decision")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("missing critic rationale")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "decision": "insufficient_evidence",
            "rationale": "critic response did not satisfy the frozen JSON contract",
        }, response
    return {"decision": decision, "rationale": rationale.strip()}, response


def _valid_report_arguments(arguments: dict[str, Any]) -> tuple[str, str] | None:
    report = arguments.get("report")
    uncertainty = arguments.get("remaining_uncertainty")
    if not isinstance(report, str) or not report.strip():
        return None
    if uncertainty not in {"low", "medium", "high"}:
        return None
    return report.strip() + "\n", uncertainty


def _load_fingerprint(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "launch_configuration",
        "llama_build",
        "model_metadata",
        "model_sha256",
        "omissions",
    }
    missing = required - set(value)
    if missing:
        raise ValueError(f"fingerprint missing keys: {sorted(missing)}")
    if not isinstance(value["omissions"], list):
        raise ValueError("fingerprint omissions must be a list")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_assessment(
    *,
    engine: ToolEngine,
    condition: Literal["baseline", "planner"],
    seed: int,
    root: Path,
    venv: Path,
    rg_path: Path,
    output_dir: Path,
    fingerprint: dict[str, Any],
    environment_validation: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=False, exist_ok=False)
    transcript_path = output_dir / "transcript.jsonl"
    report_path = output_dir / "raw-model-report.md"
    metadata_path = output_dir / "run-metadata.json"
    ledger = CoverageLedger(seed)
    passive_scopes = {name: ScopeEvidence() for name in PACKAGE_NAMES}
    started_at = utc_now()
    messages = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=USER_PROMPT),
    ]
    if condition == "planner":
        messages.append(ChatMessage(role="user", content=planner_instruction(ledger)))

    total_input = 0
    total_output = 0
    critic_input = 0
    critic_output = 0
    shell_calls = 0
    rejected_calls = 0
    critic_calls = 0
    scope_distribution = {name: 0 for name in (*PACKAGE_NAMES, "cross_repository")}
    completion_mode = "none"
    final_report: str | None = None
    remaining_uncertainty: str | None = None
    critic_records: list[dict[str, Any]] = []
    protocol_violations: list[str] = []
    turns_used = 0

    def review_findings(report: str) -> tuple[bool, list[dict[str, Any]]]:
        nonlocal critic_calls, critic_input, critic_output
        findings = extract_validated_findings(report)
        if condition != "planner" or not findings:
            return True, []
        if critic_calls + len(findings) > MAX_CRITIC_CALLS:
            return False, [
                {
                    "decision": "insufficient_evidence",
                    "rationale": "proposal exceeds the frozen three-call critic budget",
                }
            ]
        decisions = []
        for finding in findings:
            decision, response = run_critic(engine, finding, seed)
            critic_calls += 1
            critic_input += response.usage.input_tokens or 0
            critic_output += response.usage.output_tokens or 0
            record = {
                "at": utc_now(),
                "event": "critic",
                "finding_sha256": sha256_bytes(finding.encode("utf-8")),
                "decision": decision["decision"],
                "rationale": decision["rationale"],
                "usage": response.usage.model_dump(mode="json"),
                "seed_status": response.seed_status,
            }
            decisions.append(record)
            critic_records.append(record)
            append_jsonl(transcript_path, record)
        return all(item["decision"] == "accept" for item in decisions), decisions

    for turn in range(1, TURN_BUDGET + 1):
        turns_used = turn
        response = engine.generate_with_tools(
            GenerationRequest(
                messages=messages,
                max_tokens=2048,
                temperature=0,
                thinking=False,
                seed=seed,
            ),
            [SHELL_TOOL, REPORT_TOOL],
        )
        total_input += response.usage.input_tokens or 0
        total_output += response.usage.output_tokens or 0
        calls = response.message.tool_calls
        append_jsonl(
            transcript_path,
            {
                "at": utc_now(),
                "event": "assistant",
                "turn": turn,
                "content": response.text,
                "finish_reason": response.finish_reason,
                "seed_status": response.seed_status,
                "usage": response.usage.model_dump(mode="json"),
                "tool_calls": [call.model_dump(mode="json") for call in calls],
                "controller": ledger.snapshot() if condition == "planner" else None,
            },
        )
        messages.append(response.message)

        report_calls = [call for call in calls if call.name == "submit_report"]
        if report_calls:
            parsed = _valid_report_arguments(report_calls[0].arguments)
            if parsed is None:
                accepted = False
                feedback = "submit_report requires a non-empty report and valid uncertainty enum"
            else:
                candidate, uncertainty = parsed
                if (
                    condition == "planner"
                    and uncertainty == "low"
                    and ledger.covered_count < MIN_LOW_UNCERTAINTY_COVERAGE
                ):
                    accepted = False
                    feedback = "low uncertainty is unavailable below substantive coverage 8/9"
                else:
                    accepted, decisions = review_findings(candidate)
                    feedback = tool_output({"critic_decisions": decisions})
                    if accepted:
                        final_report = candidate
                        remaining_uncertainty = uncertainty
                        completion_mode = "natural"
                        break
            rejected_calls += 1
            messages.append(
                ChatMessage(
                    role="tool",
                    name="submit_report",
                    tool_call_id=report_calls[0].call_id,
                    content=tool_output({"accepted": False, "reason": feedback}),
                )
            )
            messages.append(
                ChatMessage(
                    role="user",
                    content="Revise the proposed report using the controller or critic feedback.",
                )
            )
            continue

        if not calls:
            messages.append(
                ChatMessage(
                    role="user",
                    content="Continue investigating with shell, or call submit_report when complete.",
                )
            )
            continue

        advanced = False
        for call in calls:
            if call.name != "shell":
                rejected_calls += 1
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.call_id,
                        content=tool_output({"error": f"unknown tool {call.name!r}"}),
                    )
                )
                continue
            command = call.arguments.get("command")
            if not isinstance(command, str) or not command.strip():
                rejected_calls += 1
                result = {"error": "shell requires a non-empty command"}
            elif condition == "planner" and not ledger.command_matches_current_scope(command):
                rejected_calls += 1
                result = {
                    "error": "command rejected by controller: explicitly name the assigned package path",
                    "assigned_scope": ledger.current_scope,
                }
            else:
                shell_calls += 1
                scope_distribution[attributed_scope(command)] += 1
                result = run_shell(root, venv, rg_path, command)
                observe_passive_coverage(passive_scopes, command, result)
                if condition == "planner":
                    advanced = ledger.observe(command, result) or advanced
            append_jsonl(
                transcript_path,
                {
                    "at": utc_now(),
                    "event": "tool",
                    "turn": turn,
                    "tool": "shell",
                    "call_id": call.call_id,
                    "result": result,
                    "controller": ledger.snapshot() if condition == "planner" else None,
                },
            )
            messages.append(
                ChatMessage(
                    role="tool",
                    name="shell",
                    tool_call_id=call.call_id,
                    content=tool_output(result),
                )
            )
        if condition == "planner" and advanced:
            messages.append(ChatMessage(role="user", content=planner_instruction(ledger)))

    if final_report is None:
        draft = engine.generate_with_tools(
            GenerationRequest(
                messages=messages
                + [
                    ChatMessage(
                        role="user",
                        content=(
                            "The investigation turn budget is exhausted. Do not inspect further. "
                            "Submit the complete report now using submit_report and state uncertainty."
                        ),
                    )
                ],
                max_tokens=4096,
                temperature=0,
                thinking=False,
                seed=seed,
            ),
            [REPORT_TOOL],
        )
        total_input += draft.usage.input_tokens or 0
        total_output += draft.usage.output_tokens or 0
        append_jsonl(
            transcript_path,
            {
                "at": utc_now(),
                "event": "forced_report",
                "turn": TURN_BUDGET + 1,
                "content": draft.text,
                "finish_reason": draft.finish_reason,
                "seed_status": draft.seed_status,
                "usage": draft.usage.model_dump(mode="json"),
                "tool_calls": [call.model_dump(mode="json") for call in draft.message.tool_calls],
            },
        )
        report_calls = [call for call in draft.message.tool_calls if call.name == "submit_report"]
        parsed = _valid_report_arguments(report_calls[0].arguments) if report_calls else None
        if parsed is not None:
            final_report, remaining_uncertainty = parsed
            accepted, decisions = review_findings(final_report)
            if not accepted:
                protocol_violations.append("forced report contains critic-unaccepted findings")
                append_jsonl(
                    transcript_path,
                    {
                        "at": utc_now(),
                        "event": "forced_report_critic_result",
                        "decisions": decisions,
                    },
                )
        elif draft.text.strip():
            final_report = draft.text.strip() + "\n"
            protocol_violations.append("forced report did not use the structured report contract")
        else:
            final_report = "# Repository assessment\n\nNo report was produced.\n"
            protocol_violations.append("forced report was empty")
        completion_mode = "forced"

    report_path.write_text(final_report, encoding="utf-8")
    finished_at = utc_now()
    transcript_sha256 = sha256_bytes(transcript_path.read_bytes())
    report_sha256 = sha256_bytes(report_path.read_bytes())
    metadata = {
        "schema": "temporary-repository-assessment-planner-run/v1",
        "condition": condition,
        "seed": seed,
        "started_at": started_at,
        "finished_at": finished_at,
        "target_commit": TARGET_COMMIT,
        "target_archive_sha256": TARGET_ARCHIVE_SHA256,
        "model": fingerprint["model_metadata"].get("model_label"),
        "fingerprint": fingerprint,
        "base_url_retained": False,
        "thinking": False,
        "temperature": 0,
        "turn_budget": TURN_BUDGET,
        "turns_used": turns_used,
        "turn_cap_bound": completion_mode == "forced",
        "completion_mode": completion_mode,
        "lifecycle": "final" if completion_mode == "natural" else "aborted",
        "shell_tool_calls": shell_calls,
        "rejected_tool_calls": rejected_calls,
        "scope_call_distribution": scope_distribution,
        "substantive_coverage": passive_coverage_snapshot(passive_scopes),
        "coverage": ledger.snapshot() if condition == "planner" else None,
        "remaining_uncertainty": remaining_uncertainty,
        "critic": {
            "calls": critic_calls,
            "input_tokens": critic_input,
            "output_tokens": critic_output,
            "records": critic_records,
        },
        "investigator_usage": {"input_tokens": total_input, "output_tokens": total_output},
        "protocol_violations": protocol_violations,
        "prompt_sha256": sha256_bytes(SYSTEM_PROMPT.encode("utf-8")),
        "transcript_sha256": transcript_sha256,
        "report_sha256": report_sha256,
        "sandbox": {
            "engine": "bubblewrap",
            "host_fallback": False,
            "network_unshared": True,
            "private_tmp": True,
            "repository_read_only": True,
            "validation": environment_validation,
        },
    }
    _write_json(metadata_path, metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=("baseline", "planner"), required=True)
    parser.add_argument("--seed", type=int, choices=sorted(VALID_SEEDS), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--rg", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--fingerprint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(f"refusing to overwrite {args.output_dir}")
    if not args.root.is_dir() or not args.venv.is_dir() or not args.rg.is_file():
        parser.error("root, venv, or rg path is invalid")
    fingerprint = _load_fingerprint(args.fingerprint)
    environment_validation = validate_sandbox(args.root, args.venv, args.rg)
    if not environment_validation["valid"]:
        args.output_dir.mkdir(parents=False, exist_ok=False)
        invalid = {
            "schema": "temporary-repository-assessment-planner-run/v1",
            "condition": args.condition,
            "seed": args.seed,
            "lifecycle": "aborted",
            "validity": "invalid",
            "invalid_reason": "sandbox validation failed before model execution",
            "target_commit": TARGET_COMMIT,
            "target_archive_sha256": TARGET_ARCHIVE_SHA256,
            "sandbox_validation": environment_validation,
        }
        _write_json(args.output_dir / "run-metadata.json", invalid)
        print(json.dumps(invalid, indent=2, sort_keys=True))
        return 2
    engine = OpenAIEngine(
        model=args.model,
        api_key="not-required",
        base_url=args.base_url,
        is_cloud=False,
        timeout=180,
    )
    metadata = run_assessment(
        engine=engine,
        condition=args.condition,
        seed=args.seed,
        root=args.root,
        venv=args.venv,
        rg_path=args.rg,
        output_dir=args.output_dir,
        fingerprint=fingerprint,
        environment_validation=environment_validation,
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
