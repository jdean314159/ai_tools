"""Run the preregistered fresh-context staged repository assessment.

This is experiment-specific tooling. It deliberately does not implement the
deferred production ``repository-assessment/v1`` artifact profile.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import time
from typing import Any, Protocol

from llm_engines.backends.openai import OpenAIEngine
from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    ToolParameterSchema,
    ToolSpec,
)


_BASE_PATH = Path(__file__).with_name("run_planner_assessment.py")
_BASE_SPEC = importlib.util.spec_from_file_location("repository_assessment_base", _BASE_PATH)
if _BASE_SPEC is None or _BASE_SPEC.loader is None:  # pragma: no cover - import invariant
    raise RuntimeError(f"cannot load maintained assessment harness: {_BASE_PATH}")
base = importlib.util.module_from_spec(_BASE_SPEC)
sys.modules.setdefault(_BASE_SPEC.name, base)
_BASE_SPEC.loader.exec_module(base)


TARGET_COMMIT = base.TARGET_COMMIT
TARGET_ARCHIVE_SHA256 = base.TARGET_ARCHIVE_SHA256
PACKAGE_NAMES = base.PACKAGE_NAMES
VALID_SEEDS = base.VALID_SEEDS
SHELL_CALL_CEILING = 45
SCOUT_SHELL_BUDGET = 3
VERIFIER_SHELL_BUDGET = 3
MAX_CANDIDATES = 6
MAX_STAGE_MODEL_CALLS = 5
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def normalize_target_identity(identity: dict[str, str] | None = None) -> dict[str, str]:
    if identity is None:
        return {
            "target_commit": TARGET_COMMIT,
            "target_archive_sha256": TARGET_ARCHIVE_SHA256,
        }
    expected = {"target_commit", "target_tree", "target_archive_sha256"}
    if set(identity) != expected:
        raise ValueError(f"target identity must contain exactly: {sorted(expected)}")
    normalized = {key: str(value).strip().lower() for key, value in identity.items()}
    if not _COMMIT_RE.fullmatch(normalized["target_commit"]):
        raise ValueError("target_commit must be a full lowercase Git object ID")
    if not _COMMIT_RE.fullmatch(normalized["target_tree"]):
        raise ValueError("target_tree must be a full lowercase Git object ID")
    if not _SHA256_RE.fullmatch(normalized["target_archive_sha256"]):
        raise ValueError("target_archive_sha256 must be a lowercase SHA-256 digest")
    return normalized


def target_identity_from_args(args: argparse.Namespace) -> dict[str, str]:
    values = (args.target_commit, args.target_tree, args.target_archive_sha256)
    if not any(values):
        return normalize_target_identity()
    if not all(values):
        raise ValueError(
            "--target-commit, --target-tree, and --target-archive-sha256 are all required together"
        )
    return normalize_target_identity(
        {
            "target_commit": args.target_commit,
            "target_tree": args.target_tree,
            "target_archive_sha256": args.target_archive_sha256,
        }
    )


SCOUT_SYSTEM_PROMPT = """You are one package scout in a staged, read-only repository assessment.

Your job is not to summarize the package. Find at most one real, currently actionable defect in
correctness, data integrity, security boundaries, persistence, concurrency, packaging, or a public
contract. Work from current code and observable behavior.

Required process:
1. inspect production source and a distinct test, caller, README, or package contract;
2. state a falsifiable expected behavior and suspected violation;
3. trace the relevant path end/contract and actively try to disprove the hypothesis;
4. submit one candidate only if evidence survives that attempt; otherwise submit no_candidate.

Do not report style preferences, missing tests by themselves, speculative features, or documented
limitations. Do not inspect historical status, handoff, roadmap, or experiment documents. The shell is
isolated: /workspace is read-only, /tmp is private and writable, and networking is unavailable.
Use shell only for empirical inspection. Use submit_scope_report to finish.
"""

VERIFIER_SYSTEM_PROMPT = """You are a fresh-context defect verifier in a staged, read-only assessment.

Independently verify or falsify the supplied scout candidate. Inspect the complete relevant call
path and contract. Prefer a focused non-destructive reproducer when feasible. Actively search for
guards, invariants, callers, or tests that disprove the claim. Do not broaden into a general review
and do not introduce a different finding. Return confirmed only when direct evidence demonstrates
both the behavior and an actionable impact; otherwise return rejected or insufficient_evidence.

Do not inspect historical status, handoff, roadmap, or experiment documents. /workspace is
read-only, /tmp is private and writable, and networking is unavailable. Use submit_verification to
finish.
"""

SYNTHESIS_SYSTEM_PROMPT = """You are the final synthesizer for a staged repository assessment.

Use only the controller records supplied by the user. Report only findings whose critic decision is
accept. Do not add, merge, strengthen, or infer any repository finding. Clearly separate accepted
findings, rejected or insufficient candidates, commands/tests represented in the records, coverage,
and remaining uncertainty. If no finding is accepted, say so explicitly. Use submit_synthesis.
"""

SCOUT_REPORT_TOOL = ToolSpec(
    name="submit_scope_report",
    description="Finish this package scope with one candidate or no candidate.",
    parameters={
        "disposition": ToolParameterSchema(
            type="string",
            enum=["candidate", "no_candidate"],
            description="Whether one defect candidate survived the scout's disconfirmation attempt.",
        ),
        "severity": ToolParameterSchema(
            type="string",
            enum=["critical", "high", "medium", "low", "none"],
            description="Candidate severity, or none when disposition is no_candidate.",
        ),
        "expected_behavior": ToolParameterSchema(
            type="string", description="The concrete behavior required by the contract."
        ),
        "suspected_violation": ToolParameterSchema(
            type="string", description="The observed violation, or why none survived."
        ),
        "symbols": ToolParameterSchema(
            type="string", description="Relevant files, symbols, or call path."
        ),
        "evidence": ToolParameterSchema(
            type="string", description="Direct code, test, or reproducer evidence."
        ),
        "disconfirmation_attempt": ToolParameterSchema(
            type="string", description="The check performed to try to falsify the candidate."
        ),
    },
    required_params=[
        "disposition",
        "severity",
        "expected_behavior",
        "suspected_violation",
        "symbols",
        "evidence",
        "disconfirmation_attempt",
    ],
)

VERIFICATION_TOOL = ToolSpec(
    name="submit_verification",
    description="Finish independent verification of the supplied candidate.",
    parameters={
        "decision": ToolParameterSchema(
            type="string",
            enum=["confirmed", "rejected", "insufficient_evidence"],
            description="Independent disposition of the supplied candidate.",
        ),
        "claim": ToolParameterSchema(type="string", description="Precisely bounded defect claim."),
        "symbols": ToolParameterSchema(
            type="string", description="Verified files, symbols, or call path."
        ),
        "impact": ToolParameterSchema(type="string", description="Concrete actionable impact."),
        "evidence": ToolParameterSchema(
            type="string", description="Direct verification evidence and outcomes."
        ),
        "disconfirmation_attempt": ToolParameterSchema(
            type="string", description="The strongest attempted falsification and its result."
        ),
        "remediation": ToolParameterSchema(
            type="string", description="Minimal remediation direction, or none if rejected."
        ),
    },
    required_params=[
        "decision",
        "claim",
        "symbols",
        "impact",
        "evidence",
        "disconfirmation_attempt",
        "remediation",
    ],
)

SYNTHESIS_TOOL = ToolSpec(
    name="submit_synthesis",
    description="Submit the final Markdown narrative without adding findings.",
    parameters={
        "report": ToolParameterSchema(
            type="string", description="Final Markdown narrative using only controller records."
        )
    },
    required_params=["report"],
)

_INSPECTION_RE = re.compile(r"(^|[;&|]\s*)(cat|sed|head|tail|rg|grep|awk)\b")
_PATH_TOKEN_RE = re.compile(
    r"(?:/workspace/)?(?:[A-Za-z0-9_.*/-]+\.py|[A-Za-z0-9_.*/-]*README\.md|"
    r"[A-Za-z0-9_.*/-]*pyproject\.toml)"
)


class ToolEngine(Protocol):
    def generate_with_tools(
        self, request: GenerationRequest, available_tools: list[ToolSpec]
    ) -> GenerationResponse: ...

    def generate(self, request: GenerationRequest) -> GenerationResponse: ...


@dataclass
class UsageTotal:
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0

    def observe(self, response: GenerationResponse) -> None:
        self.input_tokens += response.usage.input_tokens or 0
        self.output_tokens += response.usage.output_tokens or 0
        self.model_calls += 1

    def snapshot(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model_calls": self.model_calls,
        }


@dataclass
class ScopeTrace:
    scope: str
    commands: list[dict[str, Any]] = field(default_factory=list)

    @property
    def shell_calls(self) -> int:
        return len(self.commands)

    def coverage(self) -> dict[str, Any]:
        production: set[str] = set()
        corroborating: set[str] = set()
        for item in self.commands:
            command = item["command"]
            result = item["result"]
            if not _successful_inspection(command, result):
                continue
            for path in normalized_command_paths(command, self.scope):
                if _is_production_path(self.scope, path):
                    production.add(path)
                if _is_corroborating_path(self.scope, path):
                    corroborating.add(path)
        return {
            "covered": bool(production and corroborating),
            "production_reads": sorted(production),
            "corroborating_reads": sorted(corroborating),
        }


def _successful_inspection(command: str, result: dict[str, Any]) -> bool:
    return bool(
        _INSPECTION_RE.search(command)
        and result.get("returncode") == 0
        and result.get("stdout_length", 0) > 0
    )


def normalized_command_paths(command: str, assigned_scope: str) -> set[str]:
    """Normalize literal file paths for controller-owned coverage accounting."""
    cwd_scope = assigned_scope if f"cd /workspace/{assigned_scope}" in command else None
    paths: set[str] = set()
    for raw in _PATH_TOKEN_RE.findall(command):
        token = raw.rstrip(".,:;)")
        if token.startswith("/workspace/"):
            paths.add(token)
        elif token.startswith(f"{assigned_scope}/"):
            paths.add(f"/workspace/{token}")
        elif cwd_scope is not None and token.startswith(("src/", "tests/", "README", "pyproject")):
            paths.add(f"/workspace/{assigned_scope}/{token}")
        elif token.startswith(("src/", "tests/", "README", "pyproject")):
            paths.add(f"/workspace/{assigned_scope}/{token}")
        elif assigned_scope in token and token.startswith("tests/"):
            paths.add(f"/workspace/{token}")
    return paths


def _is_production_path(scope: str, path: str) -> bool:
    if scope == "mail_lib":
        relative = path.removeprefix("/workspace/mail_lib/")
        return relative.endswith(".py") and "/" not in relative
    return path.startswith(f"/workspace/{scope}/src/") and path.endswith(".py")


def _is_corroborating_path(scope: str, path: str) -> bool:
    prefix = f"/workspace/{scope}/"
    if path in {prefix + "README.md", prefix + "pyproject.toml"}:
        return True
    if path.startswith(prefix + "tests/") and path.endswith(".py"):
        return True
    return path.startswith("/workspace/tests/") and scope in path and path.endswith(".py")


def sanitized_sandbox_argv(root: Path, venv: Path, rg_path: Path, command: str) -> list[str]:
    argv = base.sandbox_argv(root, venv, rg_path, command)
    root_destination_index = argv.index("/workspace")
    overlay = [
        "--tmpfs",
        "/workspace/docs/internal",
        "--tmpfs",
        "/workspace/docs/projects",
    ]
    return argv[: root_destination_index + 1] + overlay + argv[root_destination_index + 1 :]


def run_sanitized_shell(root: Path, venv: Path, rg_path: Path, command: str) -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.Popen(
        sanitized_sandbox_argv(root, venv, rg_path, command),
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
    stdout_value, stdout_clipped, stdout_length = base.clipped(stdout)
    stderr_value, stderr_clipped, stderr_length = base.clipped(stderr)
    return {
        "command": command,
        "returncode": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout": stdout_value,
        "stderr": stderr_value,
        "stdout_clipped": stdout_clipped,
        "stderr_clipped": stderr_clipped,
        "stdout_length": stdout_length,
        "stderr_length": stderr_length,
    }


def validate_sanitized_sandbox(root: Path, venv: Path, rg_path: Path) -> dict[str, Any]:
    base_validation = base.validate_sandbox(root, venv, rg_path)
    mask_result = run_sanitized_shell(
        root,
        venv,
        rg_path,
        'python -c "from pathlib import Path; import json; '
        "print(json.dumps({'internal_empty': not any(Path('/workspace/docs/internal').iterdir()), "
        "'projects_empty': not any(Path('/workspace/docs/projects').iterdir()), "
        "'agent_instructions_visible': Path('/workspace/AGENTS.md').is_file()}))\"",
    )
    try:
        masks = json.loads(mask_result.get("stdout", ""))
    except (TypeError, json.JSONDecodeError):
        masks = {}
    valid_masks = all(
        masks.get(key) is True
        for key in ("internal_empty", "projects_empty", "agent_instructions_visible")
    )
    return {
        "valid": base_validation["valid"] and mask_result.get("returncode") == 0 and valid_masks,
        "base": base_validation,
        "masks": masks,
        "mask_stderr": mask_result.get("stderr", ""),
    }


def scope_order(seed: int) -> list[str]:
    order = list(PACKAGE_NAMES)
    random.Random(seed).shuffle(order)
    return order


def select_candidates(scope_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select the first six valid candidates in the frozen scope order."""
    return [item for item in scope_results if item.get("disposition") == "candidate"][
        :MAX_CANDIDATES
    ]


def controller_uncertainty(covered_count: int) -> str:
    if covered_count >= 9:
        return "low"
    if covered_count == 8:
        return "medium"
    return "high"


def _nonempty_strings(arguments: dict[str, Any], names: tuple[str, ...]) -> bool:
    return all(isinstance(arguments.get(name), str) and arguments[name].strip() for name in names)


def valid_scope_report(arguments: dict[str, Any], scope: str) -> dict[str, Any] | None:
    disposition = arguments.get("disposition")
    severity = arguments.get("severity")
    fields = (
        "expected_behavior",
        "suspected_violation",
        "symbols",
        "evidence",
        "disconfirmation_attempt",
    )
    if disposition not in {"candidate", "no_candidate"} or not _nonempty_strings(arguments, fields):
        return None
    if severity not in {"critical", "high", "medium", "low", "none"}:
        return None
    if disposition == "candidate" and severity == "none":
        return None
    if disposition == "no_candidate" and severity != "none":
        return None
    return {"scope": scope, **{key: arguments[key].strip() for key in arguments}}


def valid_verification(
    arguments: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any] | None:
    decision = arguments.get("decision")
    fields = ("claim", "symbols", "impact", "evidence", "disconfirmation_attempt", "remediation")
    if decision not in {"confirmed", "rejected", "insufficient_evidence"}:
        return None
    if not _nonempty_strings(arguments, fields):
        return None
    return {
        "scope": candidate["scope"],
        "candidate": candidate,
        **{key: arguments[key].strip() for key in arguments},
    }


def _append_response(
    transcript: Path,
    *,
    stage: str,
    stage_id: str,
    call_number: int,
    response: GenerationResponse,
) -> None:
    base.append_jsonl(
        transcript,
        {
            "at": base.utc_now(),
            "event": "assistant",
            "stage": stage,
            "stage_id": stage_id,
            "model_call": call_number,
            "content": response.text,
            "finish_reason": response.finish_reason,
            "seed_status": response.seed_status,
            "usage": response.usage.model_dump(mode="json"),
            "tool_calls": [call.model_dump(mode="json") for call in response.message.tool_calls],
        },
    )


def _run_empirical_stage(
    *,
    engine: ToolEngine,
    seed: int,
    stage: str,
    stage_id: str,
    system_prompt: str,
    user_prompt: str,
    report_tool: ToolSpec,
    report_validator: Any,
    shell_budget: int,
    root: Path,
    venv: Path,
    rg_path: Path,
    transcript: Path,
    usage: UsageTotal,
    trace: ScopeTrace,
    total_shell_calls: list[int],
    protocol_violations: list[str],
) -> tuple[dict[str, Any], bool]:
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    base.append_jsonl(
        transcript,
        {
            "at": base.utc_now(),
            "event": "stage_start",
            "stage": stage,
            "stage_id": stage_id,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "shell_budget": shell_budget,
        },
    )
    calls_used = 0
    for model_call in range(1, MAX_STAGE_MODEL_CALLS + 1):
        response = engine.generate_with_tools(
            GenerationRequest(
                messages=messages,
                max_tokens=1536,
                temperature=0,
                thinking=False,
                seed=seed,
            ),
            [base.SHELL_TOOL, report_tool],
        )
        usage.observe(response)
        _append_response(
            transcript,
            stage=stage,
            stage_id=stage_id,
            call_number=model_call,
            response=response,
        )
        messages.append(response.message)
        for call in response.message.tool_calls:
            if call.name == report_tool.name:
                validated = report_validator(call.arguments)
                if validated is not None:
                    return validated, True
                protocol_violations.append(f"{stage_id}: invalid {report_tool.name} arguments")
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.call_id,
                        content=base.tool_output(
                            {"accepted": False, "error": "invalid report fields"}
                        ),
                    )
                )
                continue
            if call.name != "shell":
                protocol_violations.append(f"{stage_id}: unknown tool {call.name}")
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.call_id,
                        content=base.tool_output({"error": "unknown tool"}),
                    )
                )
                continue
            command = call.arguments.get("command")
            if not isinstance(command, str) or not command.strip():
                result = {"error": "shell requires a non-empty command"}
                protocol_violations.append(f"{stage_id}: invalid shell arguments")
            elif calls_used >= shell_budget or total_shell_calls[0] >= SHELL_CALL_CEILING:
                result = {"error": "stage or campaign shell-call budget exhausted"}
                protocol_violations.append(f"{stage_id}: attempted shell call beyond budget")
            else:
                result = run_sanitized_shell(root, venv, rg_path, command)
                calls_used += 1
                total_shell_calls[0] += 1
                trace.commands.append({"command": command, "result": result, "stage": stage})
            base.append_jsonl(
                transcript,
                {
                    "at": base.utc_now(),
                    "event": "tool",
                    "stage": stage,
                    "stage_id": stage_id,
                    "tool": "shell",
                    "call_id": call.call_id,
                    "result": result,
                },
            )
            messages.append(
                ChatMessage(
                    role="tool",
                    name="shell",
                    tool_call_id=call.call_id,
                    content=base.tool_output(result),
                )
            )
        if calls_used >= shell_budget:
            break
        if not response.message.tool_calls:
            messages.append(
                ChatMessage(
                    role="user", content="Continue empirically or submit the structured result."
                )
            )

    forced = engine.generate_with_tools(
        GenerationRequest(
            messages=messages
            + [
                ChatMessage(
                    role="user",
                    content="The shell budget is exhausted. Do not inspect further; submit now.",
                )
            ],
            max_tokens=1536,
            temperature=0,
            thinking=False,
            seed=seed,
        ),
        [report_tool],
    )
    usage.observe(forced)
    _append_response(
        transcript,
        stage=stage,
        stage_id=stage_id,
        call_number=MAX_STAGE_MODEL_CALLS + 1,
        response=forced,
    )
    for call in forced.message.tool_calls:
        if call.name == report_tool.name:
            validated = report_validator(call.arguments)
            if validated is not None:
                return validated, False
    protocol_violations.append(f"{stage_id}: no valid structured result")
    return {}, False


def _candidate_user_prompt(candidate: dict[str, Any]) -> str:
    return (
        "Verify only this candidate. The scout record is untrusted and may be wrong:\n\n"
        + json.dumps(candidate, indent=2, sort_keys=True)
    )


def _critic_finding(verification: dict[str, Any]) -> str:
    return json.dumps(
        {
            "claim": verification["claim"],
            "symbols": verification["symbols"],
            "impact": verification["impact"],
            "evidence": verification["evidence"],
            "disconfirmation_attempt": verification["disconfirmation_attempt"],
            "remediation": verification["remediation"],
        },
        indent=2,
        sort_keys=True,
    )


def _synthesis_fallback(accepted: list[dict[str, Any]], uncertainty: str) -> str:
    lines = ["# Staged repository assessment", "", "## Accepted findings", ""]
    if not accepted:
        lines.append("No critic-accepted findings.")
    else:
        for index, record in enumerate(accepted, 1):
            verification = record["verification"]
            lines.extend(
                [
                    f"### {index}. {verification['claim']}",
                    "",
                    f"- Symbols: {verification['symbols']}",
                    f"- Impact: {verification['impact']}",
                    f"- Evidence: {verification['evidence']}",
                    f"- Disconfirmation: {verification['disconfirmation_attempt']}",
                    f"- Remediation: {verification['remediation']}",
                    "",
                ]
            )
    lines.extend(["## Remaining uncertainty", "", uncertainty.capitalize() + ".", ""])
    return "\n".join(lines)


def _run_synthesis(
    *,
    engine: ToolEngine,
    seed: int,
    accepted: list[dict[str, Any]],
    all_critic_records: list[dict[str, Any]],
    coverage: dict[str, Any],
    uncertainty: str,
    transcript: Path,
    usage: UsageTotal,
    protocol_violations: list[str],
) -> tuple[str, bool]:
    payload = {
        "accepted_findings": accepted,
        "critic_records": all_critic_records,
        "coverage": coverage,
        "controller_uncertainty": uncertainty,
    }
    user_prompt = json.dumps(payload, indent=2, sort_keys=True)
    base.append_jsonl(
        transcript,
        {
            "at": base.utc_now(),
            "event": "stage_start",
            "stage": "synthesis",
            "stage_id": "synthesis",
            "system_prompt": SYNTHESIS_SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "shell_budget": 0,
        },
    )
    response = engine.generate_with_tools(
        GenerationRequest(
            messages=[
                ChatMessage(role="system", content=SYNTHESIS_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_prompt),
            ],
            max_tokens=3072,
            temperature=0,
            thinking=False,
            seed=seed,
        ),
        [SYNTHESIS_TOOL],
    )
    usage.observe(response)
    _append_response(
        transcript,
        stage="synthesis",
        stage_id="synthesis",
        call_number=1,
        response=response,
    )
    for call in response.message.tool_calls:
        report = call.arguments.get("report") if call.name == SYNTHESIS_TOOL.name else None
        if isinstance(report, str) and report.strip():
            return report.strip() + "\n", True
    protocol_violations.append("synthesis: no valid structured report; controller fallback used")
    return _synthesis_fallback(accepted, uncertainty), False


def run_staged_assessment(
    *,
    engine: ToolEngine,
    seed: int,
    root: Path,
    venv: Path,
    rg_path: Path,
    output_dir: Path,
    fingerprint: dict[str, Any],
    environment_validation: dict[str, Any],
    target_identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    target = normalize_target_identity(target_identity)
    output_dir.mkdir(parents=False, exist_ok=False)
    transcript = output_dir / "transcript.jsonl"
    report_path = output_dir / "raw-model-report.md"
    metadata_path = output_dir / "run-metadata.json"
    started_at = base.utc_now()
    usage = UsageTotal()
    total_shell_calls = [0]
    protocol_violations: list[str] = []
    traces = {scope: ScopeTrace(scope) for scope in PACKAGE_NAMES}
    scout_results: list[dict[str, Any]] = []
    scout_structured = 0

    order = scope_order(seed)
    for scope in order:
        result, natural = _run_empirical_stage(
            engine=engine,
            seed=seed,
            stage="scout",
            stage_id=f"scout:{scope}",
            system_prompt=SCOUT_SYSTEM_PROMPT,
            user_prompt=(
                f"Assigned package: {scope}. Inspect /workspace/{scope}. You have at most "
                f"{SCOUT_SHELL_BUDGET} shell calls. Do not inspect other package scopes except a "
                "direct caller needed to verify this package's public behavior."
            ),
            report_tool=SCOUT_REPORT_TOOL,
            report_validator=lambda arguments, scope=scope: valid_scope_report(arguments, scope),
            shell_budget=SCOUT_SHELL_BUDGET,
            root=root,
            venv=venv,
            rg_path=rg_path,
            transcript=transcript,
            usage=usage,
            trace=traces[scope],
            total_shell_calls=total_shell_calls,
            protocol_violations=protocol_violations,
        )
        if result:
            result["structured_before_forcing"] = natural
            scout_results.append(result)
            scout_structured += 1
        else:
            scout_results.append(
                {
                    "scope": scope,
                    "disposition": "no_result",
                    "structured_before_forcing": False,
                }
            )

    candidates = select_candidates(scout_results)
    verifications: list[dict[str, Any]] = []
    verifier_structured = 0
    for index, candidate in enumerate(candidates, 1):
        scope = candidate["scope"]
        result, natural = _run_empirical_stage(
            engine=engine,
            seed=seed,
            stage="verifier",
            stage_id=f"verifier:{index}:{scope}",
            system_prompt=VERIFIER_SYSTEM_PROMPT,
            user_prompt=_candidate_user_prompt(candidate),
            report_tool=VERIFICATION_TOOL,
            report_validator=lambda arguments, candidate=candidate: valid_verification(
                arguments, candidate
            ),
            shell_budget=VERIFIER_SHELL_BUDGET,
            root=root,
            venv=venv,
            rg_path=rg_path,
            transcript=transcript,
            usage=usage,
            trace=traces[scope],
            total_shell_calls=total_shell_calls,
            protocol_violations=protocol_violations,
        )
        if result:
            result["structured_before_forcing"] = natural
            verifications.append(result)
            verifier_structured += 1
        else:
            verifications.append(
                {
                    "scope": scope,
                    "candidate": candidate,
                    "decision": "no_result",
                    "structured_before_forcing": False,
                }
            )

    critic_records: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for index, verification in enumerate(verifications, 1):
        if verification.get("decision") != "confirmed":
            continue
        decision, response = base.run_critic(engine, _critic_finding(verification), seed)
        usage.observe(response)
        record = {
            "index": index,
            "scope": verification["scope"],
            "verification": verification,
            "decision": decision["decision"],
            "rationale": decision["rationale"],
            "usage": response.usage.model_dump(mode="json"),
        }
        critic_records.append(record)
        base.append_jsonl(
            transcript,
            {"at": base.utc_now(), "event": "critic", "stage": "critic", **record},
        )
        if decision["decision"] == "accept":
            accepted.append(record)

    coverage_scopes = {scope: traces[scope].coverage() for scope in PACKAGE_NAMES}
    coverage = {
        "covered": sum(item["covered"] for item in coverage_scopes.values()),
        "scopes": coverage_scopes,
    }
    uncertainty = controller_uncertainty(coverage["covered"])
    report, synthesis_structured = _run_synthesis(
        engine=engine,
        seed=seed,
        accepted=accepted,
        all_critic_records=critic_records,
        coverage=coverage,
        uncertainty=uncertainty,
        transcript=transcript,
        usage=usage,
        protocol_violations=protocol_violations,
    )
    report_path.write_text(report, encoding="utf-8")

    distribution = {scope: traces[scope].shell_calls for scope in PACKAGE_NAMES}
    max_calls = max(distribution.values(), default=0)
    completed = scout_structured == len(PACKAGE_NAMES) and verifier_structured == len(candidates)
    completed = completed and synthesis_structured
    metadata = {
        "schema": "temporary-repository-assessment-staged-run/v1",
        "condition": "staged_scout_verifier_critic_synthesis",
        "seed": seed,
        "started_at": started_at,
        "finished_at": base.utc_now(),
        **target,
        "model": fingerprint["model_metadata"].get("model_label"),
        "fingerprint": fingerprint,
        "base_url_retained": False,
        "thinking": False,
        "temperature": 0,
        "shell_call_ceiling": SHELL_CALL_CEILING,
        "shell_tool_calls": total_shell_calls[0],
        "shell_call_cap_bound": total_shell_calls[0] == SHELL_CALL_CEILING,
        "scope_call_distribution": distribution,
        "max_scope_concentration": (
            max_calls / total_shell_calls[0] if total_shell_calls[0] else 0.0
        ),
        "scope_order": order,
        "scouts": {
            "expected": len(PACKAGE_NAMES),
            "structured": scout_structured,
            "results": scout_results,
        },
        "candidate_selection": {
            "rule": "first six candidates in seeded scope order",
            "limit": MAX_CANDIDATES,
            "selected": len(candidates),
        },
        "verifiers": {
            "expected": len(candidates),
            "structured": verifier_structured,
            "results": verifications,
        },
        "critic": {"calls": len(critic_records), "records": critic_records},
        "accepted_findings": accepted,
        "substantive_coverage": coverage,
        "remaining_uncertainty": uncertainty,
        "completion_mode": "structured" if completed else "controller_fallback",
        "lifecycle": "final" if completed else "aborted",
        "usage": usage.snapshot(),
        "protocol_violations": protocol_violations,
        "prompt_sha256": {
            "scout": base.sha256_bytes(SCOUT_SYSTEM_PROMPT.encode("utf-8")),
            "verifier": base.sha256_bytes(VERIFIER_SYSTEM_PROMPT.encode("utf-8")),
            "synthesis": base.sha256_bytes(SYNTHESIS_SYSTEM_PROMPT.encode("utf-8")),
        },
        "transcript_sha256": base.sha256_bytes(transcript.read_bytes()),
        "report_sha256": base.sha256_bytes(report_path.read_bytes()),
        "sandbox": {
            "engine": "bubblewrap",
            "host_fallback": False,
            "network_unshared": True,
            "private_tmp": True,
            "repository_read_only": True,
            "masked_paths": ["/workspace/docs/internal", "/workspace/docs/projects"],
            "validation": environment_validation,
        },
    }
    base._write_json(metadata_path, metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, choices=sorted(VALID_SEEDS), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--rg", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--fingerprint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-commit")
    parser.add_argument("--target-tree")
    parser.add_argument("--target-archive-sha256")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(f"refusing to overwrite {args.output_dir}")
    if not args.root.is_dir() or not args.venv.is_dir() or not args.rg.is_file():
        parser.error("root, venv, or rg path is invalid")
    try:
        target_identity = target_identity_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    fingerprint = base._load_fingerprint(args.fingerprint)
    environment_validation = validate_sanitized_sandbox(args.root, args.venv, args.rg)
    if not environment_validation["valid"]:
        args.output_dir.mkdir(parents=False, exist_ok=False)
        invalid = {
            "schema": "temporary-repository-assessment-staged-run/v1",
            "condition": "staged_scout_verifier_critic_synthesis",
            "seed": args.seed,
            "lifecycle": "aborted",
            "validity": "invalid",
            "invalid_reason": "sanitized sandbox validation failed before model execution",
            **target_identity,
            "sandbox_validation": environment_validation,
        }
        base._write_json(args.output_dir / "run-metadata.json", invalid)
        print(json.dumps(invalid, indent=2, sort_keys=True))
        return 2
    engine = OpenAIEngine(
        model=args.model,
        api_key="not-required",
        base_url=args.base_url,
        is_cloud=False,
        timeout=180,
    )
    metadata = run_staged_assessment(
        engine=engine,
        seed=args.seed,
        root=args.root,
        venv=args.venv,
        rg_path=args.rg,
        output_dir=args.output_dir,
        fingerprint=fingerprint,
        environment_validation=environment_validation,
        target_identity=target_identity,
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
