"""Run one arm of the frozen Ornith empirical-probe-obligation screen.

This is experiment-specific tooling, not the deferred production
``repository-assessment/v1`` recorder. Both fresh arms expose identical tools
and use one continuous model context. The treatment alone adds and enforces a
generic empirical-probe obligation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
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


_TOOLS_DIR = Path(__file__).resolve().parent


def _load_sibling(module_name: str, filename: str) -> Any:
    path = _TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import invariant
        raise RuntimeError(f"cannot load maintained assessment helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


base = _load_sibling("probe_screen_base", "run_planner_assessment.py")
staged = _load_sibling("probe_screen_staged", "run_staged_assessment.py")


Condition = Literal["probe_optional", "probe_required"]

TARGET_IDENTITY = {
    "target_commit": "7d37920a81a9cb672c24af3a55557621e5c5009f",
    "target_tree": "0177f7c8288a42ca771084c42362ddb6f90a9640",
    "target_archive_sha256": ("02e68e5c7cb349f1c6e3011fd6f0265ebdf6a87fa753bef932fabfd271bd8769"),
}
MODEL_LABEL = "Ornith-1.5-35B-Q4_K_M.gguf"
SEED = 31
ACTION_CALL_BUDGET = 45
MODEL_TURN_CEILING = 60
PROBE_CODE_BYTE_LIMIT = 24_000
PROBE_OBSERVATION_LIMIT = 500
PROBE_FILENAME_RE = re.compile(r"[A-Za-z0-9_-]+\.py")
FORBIDDEN_TREATMENT_TERMS = ("engram", "tenant", "delet", "episode")

SHARED_SYSTEM_PROMPT = (
    base.SYSTEM_PROMPT
    + """

An instrumented run_probe tool is available for focused behavioral checks. It creates and runs a
model-authored Python file in private temporary storage, then reports whether repository code was
actually loaded. Use it when a behavioral observation would test a hypothesis more directly than
source inspection. It has the same isolation boundary and counts against the investigation budget.
"""
)

SHARED_USER_PROMPT = (
    "Assess the repository in /workspace. Begin by reading its agent instructions and current "
    "architecture/status documents, then investigate the implementation."
)

PROBE_OBLIGATION_PROMPT = """Controller condition for this run:
Before any final report can be accepted, execute at least one instrumented behavioral probe that
loads repository code and produces observable output. The report must cite the satisfying probe's
call ID and an exact excerpt of its output. This is a generic process requirement; choose what to
probe from your own repository investigation.
"""

RUN_PROBE_TOOL = ToolSpec(
    name="run_probe",
    description=(
        "Create a model-authored Python file in private /tmp and execute it inside the isolated "
        "read-only repository environment. Returns observed output and independently detected "
        "repository modules. Counts as one investigation action."
    ),
    parameters={
        "filename": ToolParameterSchema(
            type="string",
            description="Scratch filename using letters, digits, underscore, or hyphen and .py.",
        ),
        "code": ToolParameterSchema(
            type="string",
            description=(
                "Complete Python source. It must import repository code and print observations "
                "that can be cited in the final report."
            ),
        ),
    },
    required_params=["filename", "code"],
)

SCREEN_REPORT_TOOL = ToolSpec(
    name="submit_report",
    description="Submit the final repository assessment as Markdown and end the run.",
    parameters={
        "report": ToolParameterSchema(
            type="string",
            description="Complete self-contained Markdown assessment report.",
        ),
        "disposition": ToolParameterSchema(
            type="string",
            enum=["findings", "no_findings"],
            description="Whether the report retains at least one validated finding.",
        ),
        "remaining_uncertainty": ToolParameterSchema(
            type="string",
            enum=["low", "medium", "high"],
            description="Overall uncertainty after accounting for uninspected areas.",
        ),
        "probe_call_id": ToolParameterSchema(
            type="string",
            description=(
                "A satisfying run_probe call ID cited in the report, or none if the condition "
                "does not require a probe and no satisfying probe is cited."
            ),
        ),
        "probe_observation": ToolParameterSchema(
            type="string",
            description=(
                "An exact output excerpt cited in the report, or none when probe_call_id is none."
            ),
        ),
    },
    required_params=[
        "report",
        "disposition",
        "remaining_uncertainty",
        "probe_call_id",
        "probe_observation",
    ],
)


class ToolEngine(Protocol):
    def generate_with_tools(
        self, request: GenerationRequest, available_tools: list[ToolSpec]
    ) -> GenerationResponse: ...


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
class ScreenState:
    action_calls: int = 0
    shell_calls: int = 0
    probe_calls: int = 0
    rejected_tool_calls: int = 0
    rejected_report_calls: int = 0
    model_turns: int = 0
    probe_records: list[dict[str, Any]] = field(default_factory=list)
    protocol_violations: list[str] = field(default_factory=list)
    scope_distribution: dict[str, int] = field(
        default_factory=lambda: {name: 0 for name in (*base.PACKAGE_NAMES, "cross_repository")}
    )
    passive_scopes: dict[str, Any] = field(
        default_factory=lambda: {name: base.ScopeEvidence() for name in base.PACKAGE_NAMES}
    )

    @property
    def satisfying_probes(self) -> list[dict[str, Any]]:
        return [record for record in self.probe_records if record.get("satisfied") is True]


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def tool_schema_sha256(tool: ToolSpec) -> str:
    return _canonical_sha256(tool.to_openai_schema())


def controller_policy() -> dict[str, Any]:
    return {
        "schema": "temporary-probe-obligation-controller/v1",
        "action_call_budget": ACTION_CALL_BUDGET,
        "model_turn_ceiling": MODEL_TURN_CEILING,
        "probe_satisfaction": {
            "model_authored_file_under_private_tmp": True,
            "executed_in_run": True,
            "loaded_module_under_workspace": True,
            "observable_stdout_or_stderr": True,
            "report_cites_call_id": True,
            "report_cites_exact_output_excerpt": True,
        },
        "control_submission_requires_probe": False,
        "treatment_submission_requires_probe": True,
        "forced_without_satisfying_probe": "structural_noncompletion",
    }


def treatment_model_visible_strings() -> tuple[str, ...]:
    return (
        PROBE_OBLIGATION_PROMPT,
        "Final submission rejected: the required instrumented behavioral probe has not yet "
        "satisfied the controller predicate.",
    )


def treatment_language_violations() -> list[str]:
    text = "\n".join(treatment_model_visible_strings()).lower()
    return [term for term in FORBIDDEN_TREATMENT_TERMS if term in text]


def _probe_runner_source(marker: str) -> str:
    return f"""from __future__ import annotations
import json
from pathlib import Path
import runpy
import sys
import traceback

exit_code = 0
try:
    runpy.run_path(sys.argv[1], run_name="__main__")
except SystemExit as exc:
    if isinstance(exc.code, int):
        exit_code = exc.code
    elif exc.code is not None:
        print(str(exc.code), file=sys.stderr)
        exit_code = 1
except BaseException:
    traceback.print_exc()
    exit_code = 1

workspace = Path("/workspace")
loaded = set()
for module in tuple(sys.modules.values()):
    filename = getattr(module, "__file__", None)
    if not filename:
        continue
    try:
        resolved = Path(filename).resolve()
        if resolved.is_relative_to(workspace):
            loaded.add(str(resolved))
    except (OSError, RuntimeError, ValueError):
        continue
print({marker!r} + json.dumps({{"workspace_module_files": sorted(loaded)}}), file=sys.stderr)
raise SystemExit(exit_code)
"""


def _probe_sandbox_argv(
    root: Path,
    venv: Path,
    rg_path: Path,
    scratch: Path,
    filename: str,
) -> list[str]:
    command = f"/venv/bin/python /tmp/model_probe/_controller_runner.py /tmp/model_probe/{filename}"
    argv = staged.sanitized_sandbox_argv(root, venv, rg_path, command)
    command_index = max(index for index, value in enumerate(argv) if value == "/bin/bash")
    return [
        *argv[:command_index],
        "--ro-bind",
        str(scratch),
        "/tmp/model_probe",
        *argv[command_index:],
    ]


def run_instrumented_probe(
    *,
    root: Path,
    venv: Path,
    rg_path: Path,
    call_id: str,
    filename: Any,
    code: Any,
) -> dict[str, Any]:
    if not isinstance(filename, str) or not PROBE_FILENAME_RE.fullmatch(filename):
        return {
            "probe_call_id": call_id,
            "satisfied": False,
            "error": "filename must match [A-Za-z0-9_-]+.py",
            "satisfaction_failures": ["invalid_filename"],
        }
    if not isinstance(code, str) or not code.strip():
        return {
            "probe_call_id": call_id,
            "satisfied": False,
            "error": "code must be a non-empty string",
            "satisfaction_failures": ["invalid_code"],
        }
    encoded = code.encode("utf-8")
    if len(encoded) > PROBE_CODE_BYTE_LIMIT:
        return {
            "probe_call_id": call_id,
            "satisfied": False,
            "error": f"code exceeds {PROBE_CODE_BYTE_LIMIT} UTF-8 bytes",
            "satisfaction_failures": ["code_too_large"],
        }

    marker = f"__PROBE_CONTROLLER_{secrets.token_hex(16)}__"
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="repository-probe-") as scratch_value:
        scratch = Path(scratch_value)
        (scratch / filename).write_bytes(encoded)
        (scratch / "_controller_runner.py").write_text(
            _probe_runner_source(marker), encoding="utf-8"
        )
        proc = subprocess.Popen(
            _probe_sandbox_argv(root, venv, rg_path, scratch, filename),
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

    controller_record: dict[str, Any] | None = None
    observed_stderr_lines: list[str] = []
    for line in stderr.splitlines():
        if line.startswith(marker):
            try:
                parsed = json.loads(line.removeprefix(marker))
                if isinstance(parsed, dict):
                    controller_record = parsed
            except json.JSONDecodeError:
                controller_record = None
        else:
            observed_stderr_lines.append(line)
    observed_stderr = "\n".join(observed_stderr_lines)
    if stderr.endswith("\n") and observed_stderr:
        observed_stderr += "\n"
    workspace_modules = (
        controller_record.get("workspace_module_files", [])
        if isinstance(controller_record, dict)
        else []
    )
    if not isinstance(workspace_modules, list):
        workspace_modules = []
    observable_output = bool(stdout.strip() or observed_stderr.strip())
    failures = []
    if timed_out:
        failures.append("timed_out")
    if controller_record is None:
        failures.append("missing_controller_attestation")
    if not workspace_modules:
        failures.append("no_workspace_module_loaded")
    if not observable_output:
        failures.append("no_observable_output")
    stdout_value, stdout_clipped, stdout_length = base.clipped(stdout)
    stderr_value, stderr_clipped, stderr_length = base.clipped(observed_stderr)
    return {
        "probe_call_id": call_id,
        "filename": filename,
        "code_sha256": hashlib.sha256(encoded).hexdigest(),
        "returncode": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout": stdout_value,
        "stderr": stderr_value,
        "stdout_clipped": stdout_clipped,
        "stderr_clipped": stderr_clipped,
        "stdout_length": stdout_length,
        "stderr_length": stderr_length,
        "workspace_module_files": workspace_modules,
        "observed_output_present": observable_output,
        "satisfied": not failures,
        "satisfaction_failures": failures,
    }


def _report_probe_reference(
    arguments: dict[str, Any], report: str, state: ScreenState
) -> tuple[bool, str]:
    call_id = arguments.get("probe_call_id")
    observation = arguments.get("probe_observation")
    if call_id == "none" and observation == "none":
        return True, "none"
    if not isinstance(call_id, str) or not isinstance(observation, str):
        return False, "probe reference fields must be strings"
    if not (8 <= len(observation) <= PROBE_OBSERVATION_LIMIT):
        return False, "probe observation must contain 8 to 500 characters"
    matches = [
        record for record in state.satisfying_probes if record.get("probe_call_id") == call_id
    ]
    if len(matches) != 1:
        return False, "probe_call_id does not identify one satisfying in-run probe"
    record = matches[0]
    if observation not in record.get("stdout", "") and observation not in record.get("stderr", ""):
        return False, "probe observation is not an exact retained output excerpt"
    if call_id not in report or observation not in report:
        return False, "report must cite the probe call ID and exact output excerpt"
    return True, call_id


def validate_submission(
    arguments: dict[str, Any], *, condition: Condition, state: ScreenState
) -> tuple[dict[str, str] | None, str]:
    report = arguments.get("report")
    disposition = arguments.get("disposition")
    uncertainty = arguments.get("remaining_uncertainty")
    if not isinstance(report, str) or not report.strip():
        return None, "report must be a non-empty string"
    if disposition not in {"findings", "no_findings"}:
        return None, "disposition must be findings or no_findings"
    if uncertainty not in {"low", "medium", "high"}:
        return None, "remaining_uncertainty is invalid"
    findings = base.extract_validated_findings(report)
    if disposition == "findings" and not findings:
        return None, "findings disposition requires a retained finding in the report"
    if disposition == "no_findings" and findings:
        return None, "no_findings disposition conflicts with the report"
    probe_valid, probe_reference = _report_probe_reference(arguments, report, state)
    if not probe_valid:
        return None, probe_reference
    if condition == "probe_required" and probe_reference == "none":
        return None, treatment_model_visible_strings()[1]
    return (
        {
            "report": report.strip() + "\n",
            "disposition": disposition,
            "remaining_uncertainty": uncertainty,
            "probe_call_id": probe_reference,
            "probe_observation": str(arguments.get("probe_observation")),
        },
        "accepted",
    )


def _append_assistant(
    transcript: Path, turn: int, response: GenerationResponse, condition: Condition
) -> None:
    base.append_jsonl(
        transcript,
        {
            "at": base.utc_now(),
            "event": "assistant",
            "turn": turn,
            "condition": condition,
            "content": response.text,
            "finish_reason": response.finish_reason,
            "seed_status": response.seed_status,
            "usage": response.usage.model_dump(mode="json"),
            "tool_calls": [call.model_dump(mode="json") for call in response.message.tool_calls],
        },
    )


def _append_tool(
    transcript: Path,
    *,
    turn: int,
    tool: str,
    call_id: str,
    result: dict[str, Any],
) -> None:
    base.append_jsonl(
        transcript,
        {
            "at": base.utc_now(),
            "event": "tool",
            "turn": turn,
            "tool": tool,
            "call_id": call_id,
            "result": result,
        },
    )


def _forced_report(
    *,
    engine: ToolEngine,
    condition: Condition,
    seed: int,
    messages: list[ChatMessage],
    state: ScreenState,
    usage: UsageTotal,
    transcript: Path,
) -> dict[str, str] | None:
    response = engine.generate_with_tools(
        GenerationRequest(
            messages=messages
            + [
                ChatMessage(
                    role="user",
                    content=(
                        "The investigation budget is exhausted. Do not inspect further. Submit "
                        "the complete report now using submit_report and state uncertainty."
                    ),
                )
            ],
            max_tokens=4096,
            temperature=0,
            thinking=False,
            seed=seed,
        ),
        [SCREEN_REPORT_TOOL],
    )
    usage.observe(response)
    base.append_jsonl(
        transcript,
        {
            "at": base.utc_now(),
            "event": "forced_report",
            "turn": state.model_turns + 1,
            "content": response.text,
            "finish_reason": response.finish_reason,
            "seed_status": response.seed_status,
            "usage": response.usage.model_dump(mode="json"),
            "tool_calls": [call.model_dump(mode="json") for call in response.message.tool_calls],
        },
    )
    calls = [call for call in response.message.tool_calls if call.name == "submit_report"]
    if len(calls) != 1:
        state.protocol_violations.append(
            "forced report did not make exactly one submit_report call"
        )
        return None
    parsed, reason = validate_submission(calls[0].arguments, condition=condition, state=state)
    if parsed is None:
        state.protocol_violations.append(f"forced report rejected: {reason}")
    return parsed


def run_screen(
    *,
    engine: ToolEngine,
    condition: Condition,
    seed: int,
    root: Path,
    venv: Path,
    rg_path: Path,
    output_dir: Path,
    fingerprint: dict[str, Any],
    environment_validation: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=False, exist_ok=False)
    transcript = output_dir / "transcript.jsonl"
    report_path = output_dir / "raw-model-report.md"
    metadata_path = output_dir / "run-metadata.json"
    started_at = base.utc_now()
    usage = UsageTotal()
    state = ScreenState()
    messages = [
        ChatMessage(role="system", content=SHARED_SYSTEM_PROMPT),
        ChatMessage(role="user", content=SHARED_USER_PROMPT),
    ]
    if condition == "probe_required":
        messages.append(ChatMessage(role="user", content=PROBE_OBLIGATION_PROMPT))

    final: dict[str, str] | None = None
    completion_mode = "none"
    submission_gate_blocked = False

    while state.model_turns < MODEL_TURN_CEILING and state.action_calls < ACTION_CALL_BUDGET:
        state.model_turns += 1
        response = engine.generate_with_tools(
            GenerationRequest(
                messages=messages,
                max_tokens=2048,
                temperature=0,
                thinking=False,
                seed=seed,
            ),
            [base.SHELL_TOOL, RUN_PROBE_TOOL, SCREEN_REPORT_TOOL],
        )
        usage.observe(response)
        _append_assistant(transcript, state.model_turns, response, condition)
        messages.append(response.message)
        calls = response.message.tool_calls
        report_calls = [call for call in calls if call.name == "submit_report"]
        action_calls = [call for call in calls if call.name != "submit_report"]

        if report_calls and action_calls:
            state.rejected_report_calls += len(report_calls)
            state.protocol_violations.append(
                f"turn {state.model_turns}: report call mixed with investigation actions"
            )
            for call in report_calls:
                result = {
                    "accepted": False,
                    "reason": "submit_report must be called separately after observing tool output",
                }
                _append_tool(
                    transcript,
                    turn=state.model_turns,
                    tool="submit_report",
                    call_id=call.call_id,
                    result=result,
                )
                messages.append(
                    ChatMessage(
                        role="tool",
                        name="submit_report",
                        tool_call_id=call.call_id,
                        content=base.tool_output(result),
                    )
                )
            report_calls = []

        if report_calls:
            if len(report_calls) != 1:
                reason = "make exactly one submit_report call"
                parsed = None
            else:
                parsed, reason = validate_submission(
                    report_calls[0].arguments, condition=condition, state=state
                )
            if parsed is not None:
                final = parsed
                completion_mode = "natural"
                break
            state.rejected_report_calls += len(report_calls)
            if condition == "probe_required" and not state.satisfying_probes:
                submission_gate_blocked = True
            for call in report_calls:
                result = {"accepted": False, "reason": reason}
                _append_tool(
                    transcript,
                    turn=state.model_turns,
                    tool="submit_report",
                    call_id=call.call_id,
                    result=result,
                )
                messages.append(
                    ChatMessage(
                        role="tool",
                        name="submit_report",
                        tool_call_id=call.call_id,
                        content=base.tool_output(result),
                    )
                )
            messages.append(
                ChatMessage(
                    role="user", content="Revise the submission using the controller feedback."
                )
            )
            continue

        if not calls:
            messages.append(
                ChatMessage(
                    role="user",
                    content="Continue investigating, or call submit_report when complete.",
                )
            )
            continue

        for call in action_calls:
            if state.action_calls >= ACTION_CALL_BUDGET:
                result = {"error": "investigation action budget exhausted"}
                state.rejected_tool_calls += 1
            elif call.name == "shell":
                state.action_calls += 1
                state.shell_calls += 1
                command = call.arguments.get("command")
                if not isinstance(command, str) or not command.strip():
                    result = {"error": "shell requires a non-empty command"}
                    state.rejected_tool_calls += 1
                else:
                    result = staged.run_sanitized_shell(root, venv, rg_path, command)
                    state.scope_distribution[base.attributed_scope(command)] += 1
                    base.observe_passive_coverage(state.passive_scopes, command, result)
            elif call.name == "run_probe":
                state.action_calls += 1
                state.probe_calls += 1
                result = run_instrumented_probe(
                    root=root,
                    venv=venv,
                    rg_path=rg_path,
                    call_id=call.call_id,
                    filename=call.arguments.get("filename"),
                    code=call.arguments.get("code"),
                )
                state.probe_records.append(result)
                for module_path in result.get("workspace_module_files", []):
                    if not isinstance(module_path, str):
                        continue
                    state.scope_distribution[base.attributed_scope(module_path)] += 1
            else:
                state.action_calls += 1
                state.rejected_tool_calls += 1
                result = {"error": f"unknown tool {call.name!r}"}
            _append_tool(
                transcript,
                turn=state.model_turns,
                tool=call.name,
                call_id=call.call_id,
                result=result,
            )
            messages.append(
                ChatMessage(
                    role="tool",
                    name=call.name,
                    tool_call_id=call.call_id,
                    content=base.tool_output(result),
                )
            )

    if final is None:
        if condition == "probe_required" and not state.satisfying_probes:
            completion_mode = "structural_noncompletion"
        else:
            final = _forced_report(
                engine=engine,
                condition=condition,
                seed=seed,
                messages=messages,
                state=state,
                usage=usage,
                transcript=transcript,
            )
            completion_mode = "forced" if final is not None else "forced_invalid"

    if final is None:
        report = (
            "# Repository assessment\n\n"
            "No controller-accepted model report was produced. See the transcript and run metadata.\n"
        )
        disposition = None
        uncertainty = None
        report_probe_call_id = None
        report_probe_observation = None
    else:
        report = final["report"]
        disposition = final["disposition"]
        uncertainty = final["remaining_uncertainty"]
        report_probe_call_id = final["probe_call_id"]
        report_probe_observation = final["probe_observation"]
    report_path.write_text(report, encoding="utf-8")

    if completion_mode == "natural":
        outcome = (
            "natural_after_gate_block" if submission_gate_blocked else "natural_valid_submission"
        )
    elif completion_mode == "forced":
        outcome = "forced_valid_submission"
    elif completion_mode == "structural_noncompletion":
        outcome = "structural_noncompletion_probe_unsatisfied"
    else:
        outcome = "forced_invalid_submission"

    metadata = {
        "schema": "temporary-repository-assessment-probe-obligation-screen-run/v1",
        "condition": condition,
        "seed": seed,
        "started_at": started_at,
        "finished_at": base.utc_now(),
        **TARGET_IDENTITY,
        "model": fingerprint["model_metadata"].get("model_label"),
        "fingerprint": fingerprint,
        "base_url_retained": False,
        "thinking": False,
        "temperature": 0,
        "action_call_budget": ACTION_CALL_BUDGET,
        "action_calls": state.action_calls,
        "action_cap_bound": state.action_calls == ACTION_CALL_BUDGET,
        "model_turn_ceiling": MODEL_TURN_CEILING,
        "model_turns": state.model_turns,
        "model_turn_cap_bound": state.model_turns == MODEL_TURN_CEILING,
        "shell_tool_calls": state.shell_calls,
        "probe_tool_calls": state.probe_calls,
        "probe_authoring_events": state.probe_calls,
        "probe_execution_events": state.probe_calls,
        "satisfying_probe_calls": len(state.satisfying_probes),
        "probe_records": state.probe_records,
        "scope_call_distribution": state.scope_distribution,
        "substantive_coverage": base.passive_coverage_snapshot(state.passive_scopes),
        "rejected_tool_calls": state.rejected_tool_calls,
        "rejected_report_calls": state.rejected_report_calls,
        "submission_gate_blocked": submission_gate_blocked,
        "completion_mode": completion_mode,
        "outcome": outcome,
        "lifecycle": "final" if completion_mode == "natural" else "aborted",
        "report_disposition": disposition,
        "remaining_uncertainty": uncertainty,
        "report_probe_call_id": report_probe_call_id,
        "report_probe_observation": report_probe_observation,
        "usage": usage.snapshot(),
        "protocol_violations": state.protocol_violations,
        "prompt_sha256": {
            "shared_system": base.sha256_bytes(SHARED_SYSTEM_PROMPT.encode("utf-8")),
            "shared_user": base.sha256_bytes(SHARED_USER_PROMPT.encode("utf-8")),
            "probe_obligation": base.sha256_bytes(PROBE_OBLIGATION_PROMPT.encode("utf-8")),
        },
        "tool_schema_sha256": {
            "shell": tool_schema_sha256(base.SHELL_TOOL),
            "run_probe": tool_schema_sha256(RUN_PROBE_TOOL),
            "submit_report": tool_schema_sha256(SCREEN_REPORT_TOOL),
        },
        "controller_policy_sha256": _canonical_sha256(controller_policy()),
        "runner_sha256": base.sha256_bytes(Path(__file__).read_bytes()),
        "treatment_language_violations": treatment_language_violations(),
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
    parser.add_argument("--condition", choices=("probe_optional", "probe_required"), required=True)
    parser.add_argument("--seed", type=int, choices=(SEED,), required=True)
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
    if treatment_language_violations():
        parser.error("treatment-only model-visible text failed the generic-language gate")
    fingerprint = base._load_fingerprint(args.fingerprint)
    if fingerprint["model_metadata"].get("model_label") != MODEL_LABEL:
        parser.error(f"fingerprint model must be {MODEL_LABEL}")
    environment_validation = staged.validate_sanitized_sandbox(args.root, args.venv, args.rg)
    if not environment_validation["valid"]:
        args.output_dir.mkdir(parents=False, exist_ok=False)
        invalid = {
            "schema": "temporary-repository-assessment-probe-obligation-screen-run/v1",
            "condition": args.condition,
            "seed": args.seed,
            "lifecycle": "aborted",
            "validity": "invalid",
            "invalid_reason": "sanitized sandbox validation failed before model execution",
            **TARGET_IDENTITY,
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
    metadata = run_screen(
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
