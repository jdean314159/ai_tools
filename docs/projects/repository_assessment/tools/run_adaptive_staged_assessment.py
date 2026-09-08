"""Run the adaptive staged-v2.2 repository-assessment development condition.

This is experiment-specific tooling. It does not implement the deferred
production ``repository-assessment/v1`` artifact profile.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
import importlib.util
import json
from pathlib import Path
import random
import sys
from typing import Any, Protocol

from llm_engines.backends.openai import OpenAIEngine
from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    ToolParameterSchema,
    ToolSpec,
)


_V1_PATH = Path(__file__).with_name("run_staged_assessment.py")
_V1_SPEC = importlib.util.spec_from_file_location("repository_assessment_staged_v1", _V1_PATH)
if _V1_SPEC is None or _V1_SPEC.loader is None:  # pragma: no cover - import invariant
    raise RuntimeError(f"cannot load staged-v1 harness: {_V1_PATH}")
v1 = importlib.util.module_from_spec(_V1_SPEC)
sys.modules.setdefault(_V1_SPEC.name, v1)
_V1_SPEC.loader.exec_module(v1)
base = v1.base


TARGET_COMMIT = v1.TARGET_COMMIT
TARGET_ARCHIVE_SHA256 = v1.TARGET_ARCHIVE_SHA256
PACKAGE_NAMES = v1.PACKAGE_NAMES
VALID_SEEDS = v1.VALID_SEEDS
SHELL_CALL_CEILING = 45
SCOUT_SHELL_BUDGET = 2
VERIFIER_SHELL_BUDGET = 9
MAX_PROMOTED_HYPOTHESES = 3
MAX_SELECTION_ATTEMPTS = 3
MAX_MODULES = 80
MAX_SYMBOLS = 400
MAX_TESTS = 80
MAX_TEST_REFERENCES = 240
MAX_README_HEADINGS = 40
DOSSIER_SCHEMA = "temporary-repository-package-dossier/v1"
RUN_SCHEMA = "temporary-repository-assessment-adaptive-staged-run/v3"
CONDITION = "adaptive_staged_v2_2"

SELECTION_SYSTEM_PROMPT = """You are selecting one concrete hypothesis for a package assessment.

Use only the deterministic package dossier supplied below. Before receiving shell access, select
one non-trivial production symbol and state one falsifiable behavioral invariant, the repository
path expected to support that behavior (or invariant_derived), and a disconfirmation plan.

Do not choose a package, directory, glob, README, or ordinary __init__.py export as the production
target. Do not claim that missing tests or documentation are implementation defects. This is target
selection, not a finding. Use select_hypothesis exactly once.
"""

SCOUT_SYSTEM_PROMPT = """You are a focused package scout in a read-only repository assessment.

Investigate only the controller-approved hypothesis. You have two shell calls: use the first to
inspect the selected implementation and strongest repository contract, caller, or test; use the
second to trace or reproduce the behavior and actively seek a guard or fact that disproves it.
Combine related reads within a call when needed. Do not spend calls listing the repository or
re-reading the supplied dossier.

Submit supported only when direct evidence demonstrates the suspected violation, unresolved when
the evidence is incomplete, and disproved when the implementation or contract defeats it. Cite
exact short quotes from retained shell output and the stage-local evidence_id shown in that output.
Repeat the controller-approved expected_behavior_source and symbol exactly; the controller owns those
bindings. Do not introduce a different hypothesis. Use submit_hypothesis_result to finish.
"""

VERIFIER_SYSTEM_PROMPT = """You are a fresh-context defect verifier in a read-only assessment.

Independently verify only the promoted hypothesis. Locate the repository basis for expected
behavior, trace the complete call path, run a focused non-destructive reproducer when feasible, and
make the strongest practical disconfirmation attempt. You have up to nine shell calls. Do not
broaden into a general review or introduce a new finding.

Return confirmed only when transcript-linked evidence demonstrates behavior and actionable impact;
return rejected when evidence defeats the claim; otherwise return insufficient_evidence. Every
evidence quote must be an exact short substring of retained output from the cited stage-local
evidence_id. Repeat the controller-approved expected_behavior_source and symbol exactly; the
controller owns those bindings. Use submit_verification to finish.
"""


def _string_parameter(description: str, *, enum: list[str] | None = None) -> ToolParameterSchema:
    return ToolParameterSchema(type="string", description=description, enum=enum)


SELECT_HYPOTHESIS_TOOL = ToolSpec(
    name="select_hypothesis",
    description="Select one dossier-backed production symbol and falsifiable invariant.",
    parameters={
        "production_path": _string_parameter("Exact production module path from the dossier."),
        "symbol": _string_parameter("Exact class or function name from the dossier."),
        "invariant": _string_parameter("One falsifiable behavioral invariant."),
        "expected_behavior_source": _string_parameter(
            "Exact dossier path supporting expected behavior, or invariant_derived."
        ),
        "disconfirmation_plan": _string_parameter(
            "A concrete check that could show the suspected violation is not real."
        ),
    },
    required_params=[
        "production_path",
        "symbol",
        "invariant",
        "expected_behavior_source",
        "disconfirmation_plan",
    ],
)

_EVIDENCE_PARAMETERS = {
    "contract_call_id": _string_parameter(
        "Stage-local evidence_id shown in the shell output containing the contract quote."
    ),
    "contract_quote": _string_parameter("Exact short quote from the contract call output."),
    "behavior_call_id": _string_parameter(
        "Stage-local evidence_id shown in the shell output containing the behavior quote."
    ),
    "behavior_quote": _string_parameter("Exact short quote from the behavior call output."),
    "disconfirmation_call_id": _string_parameter(
        "Stage-local evidence_id shown in the shell output containing the disconfirmation quote."
    ),
    "disconfirmation_quote": _string_parameter(
        "Exact short quote showing the disconfirmation check or result."
    ),
}

HYPOTHESIS_RESULT_TOOL = ToolSpec(
    name="submit_hypothesis_result",
    description="Submit the evidence-backed disposition of the approved hypothesis.",
    parameters={
        "disposition": _string_parameter(
            "Evidence disposition.", enum=["supported", "unresolved", "disproved"]
        ),
        "claim": _string_parameter("Precisely bounded suspected behavior."),
        "expected_behavior": _string_parameter("Repository-backed expected behavior."),
        "expected_behavior_source": _string_parameter(
            "Repository source for expected behavior, or invariant_derived."
        ),
        "symbols": _string_parameter("Relevant path, symbol, and call path."),
        "impact": _string_parameter("Concrete impact, or none if disproved."),
        **_EVIDENCE_PARAMETERS,
    },
    required_params=[
        "disposition",
        "claim",
        "expected_behavior",
        "expected_behavior_source",
        "symbols",
        "impact",
        *_EVIDENCE_PARAMETERS,
    ],
)

VERIFICATION_TOOL = ToolSpec(
    name="submit_verification",
    description="Submit independent verification of the promoted hypothesis.",
    parameters={
        "decision": _string_parameter(
            "Independent disposition.",
            enum=["confirmed", "rejected", "insufficient_evidence"],
        ),
        "claim": _string_parameter("Precisely bounded defect claim."),
        "expected_behavior": _string_parameter("Repository-backed expected behavior."),
        "expected_behavior_source": _string_parameter(
            "Repository source for expected behavior, or invariant_derived."
        ),
        "symbols": _string_parameter("Verified path, symbol, and call path."),
        "impact": _string_parameter("Concrete actionable impact."),
        "remediation": _string_parameter("Minimal remediation, or none when rejected."),
        **_EVIDENCE_PARAMETERS,
    },
    required_params=[
        "decision",
        "claim",
        "expected_behavior",
        "expected_behavior_source",
        "symbols",
        "impact",
        "remediation",
        *_EVIDENCE_PARAMETERS,
    ],
)


class ToolEngine(Protocol):
    def generate_with_tools(
        self, request: GenerationRequest, available_tools: list[ToolSpec]
    ) -> GenerationResponse: ...

    def generate(self, request: GenerationRequest) -> GenerationResponse: ...


@dataclass
class StageTrace:
    stage_id: str
    scope: str
    calls: list[dict[str, Any]] = field(default_factory=list)

    def output_for(self, evidence_id: str) -> str | None:
        matches = [item for item in self.calls if item["evidence_id"] == evidence_id]
        if len(matches) != 1:
            return None
        result = matches[0]["result"]
        return f"{result.get('stdout', '')}\n{result.get('stderr', '')}"


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _production_files(root: Path, scope: str) -> list[Path]:
    package_root = root / scope
    if scope == "mail_lib":
        files = [path for path in package_root.glob("*.py") if path.is_file()]
    else:
        files = [path for path in (package_root / "src").rglob("*.py") if path.is_file()]
    return sorted(files, key=lambda path: _relative(path, root))


def _test_files(root: Path, scope: str) -> list[Path]:
    package_root = root / scope
    candidates = [path for path in (package_root / "tests").rglob("*.py") if path.is_file()]
    root_tests = root / "tests"
    if root_tests.is_dir():
        for path in root_tests.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if scope in path.name or scope in text:
                candidates.append(path)
    return sorted(set(candidates), key=lambda path: _relative(path, root))


def _module_symbols(path: Path, root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return [], []
    relative = _relative(path, root)
    symbols: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "__"
        ):
            symbols.append(
                {
                    "path": relative,
                    "name": node.name,
                    "kind": type(node).__name__,
                    "lineno": node.lineno,
                }
            )
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("__"):
            symbols.append(
                {
                    "path": relative,
                    "name": node.name,
                    "kind": "ClassDef",
                    "lineno": node.lineno,
                }
            )
            symbols.extend(
                {
                    "path": relative,
                    "name": f"{node.name}.{member.name}",
                    "kind": type(member).__name__,
                    "lineno": member.lineno,
                }
                for member in node.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not member.name.startswith("__")
            )
    exports: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
        if isinstance(value, (list, tuple)):
            exports.extend(item for item in value if isinstance(item, str))
    return symbols, exports


def build_package_dossier(root: Path, scope: str) -> dict[str, Any]:
    modules = _production_files(root, scope)
    tests = _test_files(root, scope)
    all_symbols: list[dict[str, Any]] = []
    exports: set[str] = set()
    for module in modules:
        symbols, module_exports = _module_symbols(module, root)
        all_symbols.extend(symbols)
        exports.update(module_exports)

    references: list[dict[str, str]] = []
    symbol_names = sorted({item["name"] for item in all_symbols})
    for test in tests:
        try:
            text = test.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for symbol in symbol_names:
            if symbol.rsplit(".", 1)[-1] in text:
                references.append({"test_path": _relative(test, root), "symbol": symbol})

    package_root = root / scope
    readme = package_root / "README.md"
    headings: list[str] = []
    if readme.is_file():
        headings = [
            line.strip()
            for line in readme.read_text(encoding="utf-8").splitlines()
            if line.startswith("#")
        ]
    metadata_paths = [
        _relative(path, root)
        for path in (package_root / "README.md", package_root / "pyproject.toml")
        if path.is_file()
    ]
    return {
        "schema": DOSSIER_SCHEMA,
        "scope": scope,
        "production_modules": [_relative(path, root) for path in modules[:MAX_MODULES]],
        "symbols": sorted(
            all_symbols, key=lambda item: (item["path"], item["lineno"], item["name"])
        )[:MAX_SYMBOLS],
        "exports": sorted(exports)[:MAX_SYMBOLS],
        "test_paths": [_relative(path, root) for path in tests[:MAX_TESTS]],
        "test_symbol_references": sorted(
            references, key=lambda item: (item["test_path"], item["symbol"])
        )[:MAX_TEST_REFERENCES],
        "readme_headings": headings[:MAX_README_HEADINGS],
        "metadata_paths": metadata_paths,
        "limits": {
            "modules": MAX_MODULES,
            "symbols": MAX_SYMBOLS,
            "tests": MAX_TESTS,
            "test_references": MAX_TEST_REFERENCES,
            "readme_headings": MAX_README_HEADINGS,
        },
        "truncated": {
            "modules": len(modules) > MAX_MODULES,
            "symbols": len(all_symbols) > MAX_SYMBOLS,
            "tests": len(tests) > MAX_TESTS,
            "test_references": len(references) > MAX_TEST_REFERENCES,
            "readme_headings": len(headings) > MAX_README_HEADINGS,
        },
    }


def canonical_dossier_bytes(dossier: dict[str, Any]) -> bytes:
    return (
        json.dumps(dossier, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def dossier_sha256(dossier: dict[str, Any]) -> str:
    return base.sha256_bytes(canonical_dossier_bytes(dossier))


def _nonempty_strings(arguments: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(
        isinstance(arguments.get(field), str) and arguments[field].strip() for field in fields
    )


def validate_selection(
    arguments: dict[str, Any], dossier: dict[str, Any]
) -> tuple[dict[str, str] | None, str]:
    fields = (
        "production_path",
        "symbol",
        "invariant",
        "expected_behavior_source",
        "disconfirmation_plan",
    )
    if not _nonempty_strings(arguments, fields):
        return None, "every selection field must be a non-empty string"
    selection = {field: arguments[field].strip() for field in fields}
    production_path = selection["production_path"].removeprefix("/workspace/")
    selection["production_path"] = production_path
    if production_path not in dossier["production_modules"]:
        return None, "production_path is absent from the dossier"
    if Path(production_path).name == "__init__.py":
        return None, "ordinary __init__.py exports are not valid investigation targets"
    symbol_pairs = {(item["path"], item["name"]) for item in dossier["symbols"]}
    if (production_path, selection["symbol"]) not in symbol_pairs:
        return None, "symbol is absent from the dossier at production_path"
    expected_source = selection["expected_behavior_source"].removeprefix("/workspace/")
    selection["expected_behavior_source"] = expected_source
    allowed_sources = {
        *dossier["production_modules"],
        *dossier["test_paths"],
        *dossier["metadata_paths"],
        "invariant_derived",
    }
    if expected_source not in allowed_sources:
        return None, "expected_behavior_source is absent from the dossier"
    return selection, "accepted"


def focused_dossier(dossier: dict[str, Any], selection: dict[str, str]) -> dict[str, Any]:
    symbol = selection["symbol"]
    bare_symbol = symbol.rsplit(".", 1)[-1]
    referenced_tests = sorted(
        {
            item["test_path"]
            for item in dossier["test_symbol_references"]
            if item["symbol"] in {symbol, bare_symbol}
        }
    )
    return {
        "schema": dossier["schema"],
        "scope": dossier["scope"],
        "selected_symbol": selection,
        "production_modules": dossier["production_modules"],
        "referenced_test_paths": referenced_tests,
        "metadata_paths": dossier["metadata_paths"],
        "readme_headings": dossier["readme_headings"],
    }


def validate_evidence_references(
    arguments: dict[str, Any], trace: StageTrace
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for prefix in ("contract", "behavior", "disconfirmation"):
        call_field = f"{prefix}_call_id"
        quote_field = f"{prefix}_quote"
        call_id = arguments.get(call_field)
        quote = arguments.get(quote_field)
        if not isinstance(call_id, str) or not call_id.strip():
            errors.append(f"{call_field} is missing")
            continue
        if not isinstance(quote, str) or not quote.strip():
            errors.append(f"{quote_field} is missing")
            continue
        output = trace.output_for(call_id.strip())
        if output is None:
            errors.append(f"{call_field} does not identify exactly one call in this stage")
        elif quote.strip() not in output:
            errors.append(f"{quote_field} is not an exact substring of retained output")
    return not errors, errors


def _record_response(
    transcript: Path,
    *,
    stage: str,
    stage_id: str,
    model_call: int,
    response: GenerationResponse,
) -> None:
    base.append_jsonl(
        transcript,
        {
            "at": base.utc_now(),
            "event": "assistant",
            "stage": stage,
            "stage_id": stage_id,
            "model_call": model_call,
            "content": response.text,
            "finish_reason": response.finish_reason,
            "seed_status": response.seed_status,
            "usage": response.usage.model_dump(mode="json"),
            "tool_calls": [call.model_dump(mode="json") for call in response.message.tool_calls],
        },
    )


def run_selection(
    *,
    engine: ToolEngine,
    seed: int,
    scope: str,
    dossier: dict[str, Any],
    transcript: Path,
    usage: v1.UsageTotal,
    protocol_violations: list[str],
) -> tuple[dict[str, str] | None, bool]:
    stage_id = f"selection:{scope}"
    user_prompt = json.dumps(dossier, indent=2, sort_keys=True)
    messages = [
        ChatMessage(role="system", content=SELECTION_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_prompt),
    ]
    base.append_jsonl(
        transcript,
        {
            "at": base.utc_now(),
            "event": "stage_start",
            "stage": "selection",
            "stage_id": stage_id,
            "system_prompt": SELECTION_SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "shell_budget": 0,
        },
    )
    for attempt in range(1, MAX_SELECTION_ATTEMPTS + 1):
        response = engine.generate_with_tools(
            GenerationRequest(
                messages=messages,
                max_tokens=768,
                temperature=0,
                thinking=False,
                seed=seed,
            ),
            [SELECT_HYPOTHESIS_TOOL],
        )
        usage.observe(response)
        _record_response(
            transcript,
            stage="selection",
            stage_id=stage_id,
            model_call=attempt,
            response=response,
        )
        messages.append(response.message)
        selection_calls = [
            call for call in response.message.tool_calls if call.name == SELECT_HYPOTHESIS_TOOL.name
        ]
        if selection_calls:
            selection, reason = validate_selection(selection_calls[0].arguments, dossier)
            base.append_jsonl(
                transcript,
                {
                    "at": base.utc_now(),
                    "event": "selection_validation",
                    "stage": "selection",
                    "stage_id": stage_id,
                    "attempt": attempt,
                    "accepted": selection is not None,
                    "reason": reason,
                },
            )
            if selection is not None:
                return selection, attempt == 1
            messages.append(
                ChatMessage(
                    role="tool",
                    name=SELECT_HYPOTHESIS_TOOL.name,
                    tool_call_id=selection_calls[0].call_id,
                    content=base.tool_output({"accepted": False, "reason": reason}),
                )
            )
        else:
            reason = "select_hypothesis was not called"
        messages.append(
            ChatMessage(
                role="user",
                content=f"Selection rejected: {reason}. Choose a valid dossier-backed target.",
            )
        )
    protocol_violations.append(f"{stage_id}: no valid selection after three attempts")
    return None, False


def _validated_stage_result(
    *,
    arguments: dict[str, Any],
    result_kind: str,
    selection: dict[str, str],
    trace: StageTrace,
) -> dict[str, Any] | None:
    common_fields = (
        "claim",
        "expected_behavior",
        "expected_behavior_source",
        "symbols",
        "impact",
        "contract_call_id",
        "contract_quote",
        "behavior_call_id",
        "behavior_quote",
        "disconfirmation_call_id",
        "disconfirmation_quote",
    )
    if not _nonempty_strings(arguments, common_fields):
        return None
    if result_kind == "scout":
        decision_field = "disposition"
        allowed = {"supported", "unresolved", "disproved"}
        extra_fields: tuple[str, ...] = ()
    else:
        decision_field = "decision"
        allowed = {"confirmed", "rejected", "insufficient_evidence"}
        extra_fields = ("remediation",)
    if arguments.get(decision_field) not in allowed or not _nonempty_strings(
        arguments, extra_fields
    ):
        return None
    result = {
        field: arguments[field].strip() for field in (*common_fields, *extra_fields, decision_field)
    }
    reported_source = result["expected_behavior_source"].removeprefix("/workspace/")
    selected_symbol = selection["symbol"]
    bare_symbol = selected_symbol.rsplit(".", 1)[-1]
    reported_symbols = result["symbols"]
    binding_errors = []
    if reported_source != selection["expected_behavior_source"]:
        binding_errors.append(
            "reported expected_behavior_source differed from controller selection"
        )
    if selected_symbol not in reported_symbols and bare_symbol not in reported_symbols:
        binding_errors.append("reported symbols omitted the controller-selected symbol")
    result["reported_expected_behavior_source"] = reported_source
    result["expected_behavior_source"] = selection["expected_behavior_source"]
    result["reported_symbols"] = reported_symbols
    result["symbols"] = f"{selection['production_path']}::{selection['symbol']}"
    result["selection_binding"] = {"valid": not binding_errors, "errors": binding_errors}
    evidence_valid, evidence_errors = validate_evidence_references(result, trace)
    result["selection"] = selection
    result["scope"] = trace.scope
    result["evidence_validation"] = {"valid": evidence_valid, "errors": evidence_errors}
    positive_decision = result[decision_field] == (
        "supported" if result_kind == "scout" else "confirmed"
    )
    if positive_decision and (not evidence_valid or binding_errors):
        result[f"original_{decision_field}"] = result[decision_field]
        result[decision_field] = "unresolved" if result_kind == "scout" else "insufficient_evidence"
    return result


def run_empirical_stage(
    *,
    engine: ToolEngine,
    seed: int,
    stage: str,
    scope: str,
    stage_id: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    selection: dict[str, str],
    report_tool: ToolSpec,
    shell_budget: int,
    root: Path,
    venv: Path,
    rg_path: Path,
    transcript: Path,
    usage: v1.UsageTotal,
    total_shell_calls: list[int],
    protocol_violations: list[str],
) -> tuple[dict[str, Any], bool, StageTrace]:
    user_prompt = json.dumps(user_payload, indent=2, sort_keys=True)
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    trace = StageTrace(stage_id=stage_id, scope=scope)
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
    model_call = 0
    shell_calls = 0
    while model_call < shell_budget + 3:
        model_call += 1
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
        _record_response(
            transcript,
            stage=stage,
            stage_id=stage_id,
            model_call=model_call,
            response=response,
        )
        messages.append(response.message)
        report_calls = []
        for call in response.message.tool_calls:
            if call.name == report_tool.name:
                report_calls.append(call)
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
            elif shell_calls >= shell_budget or total_shell_calls[0] >= SHELL_CALL_CEILING:
                result = {"error": "stage or campaign shell-call budget exhausted"}
                protocol_violations.append(f"{stage_id}: attempted shell call beyond budget")
            else:
                result = v1.run_sanitized_shell(root, venv, rg_path, command)
                shell_calls += 1
                total_shell_calls[0] += 1
                evidence_id = f"shell-{shell_calls}"
                result = {"evidence_id": evidence_id, **result}
                trace.calls.append(
                    {
                        "evidence_id": evidence_id,
                        "tool_call_id": call.call_id,
                        "command": command,
                        "result": result,
                    }
                )
            base.append_jsonl(
                transcript,
                {
                    "at": base.utc_now(),
                    "event": "tool",
                    "stage": stage,
                    "stage_id": stage_id,
                    "tool": "shell",
                    "tool_call_id": call.call_id,
                    "evidence_id": result.get("evidence_id"),
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
        if report_calls:
            validated = _validated_stage_result(
                arguments=report_calls[0].arguments,
                result_kind=stage,
                selection=selection,
                trace=trace,
            )
            if validated is not None:
                return validated, True, trace
            protocol_violations.append(f"{stage_id}: invalid {report_tool.name} arguments")
            messages.append(
                ChatMessage(
                    role="tool",
                    name=report_tool.name,
                    tool_call_id=report_calls[0].call_id,
                    content=base.tool_output({"accepted": False, "error": "invalid result fields"}),
                )
            )
        if shell_calls >= shell_budget:
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
    _record_response(
        transcript,
        stage=stage,
        stage_id=stage_id,
        model_call=model_call + 1,
        response=forced,
    )
    report_calls = [call for call in forced.message.tool_calls if call.name == report_tool.name]
    if report_calls:
        validated = _validated_stage_result(
            arguments=report_calls[0].arguments,
            result_kind=stage,
            selection=selection,
            trace=trace,
        )
        if validated is not None:
            return validated, False, trace
    protocol_violations.append(f"{stage_id}: no valid structured result")
    return {}, False, trace


def promote_hypotheses(results: list[dict[str, Any]], order: list[str]) -> list[dict[str, Any]]:
    rank = {"supported": 0, "unresolved": 1}
    order_index = {scope: index for index, scope in enumerate(order)}
    promotable = [item for item in results if item.get("disposition") in rank]
    promotable.sort(key=lambda item: (rank[item["disposition"]], order_index[item["scope"]]))
    return promotable[:MAX_PROMOTED_HYPOTHESES]


def _critic_payload(verification: dict[str, Any]) -> str:
    keys = (
        "claim",
        "expected_behavior",
        "expected_behavior_source",
        "symbols",
        "impact",
        "contract_quote",
        "behavior_quote",
        "disconfirmation_quote",
        "remediation",
    )
    return json.dumps({key: verification[key] for key in keys}, indent=2, sort_keys=True)


def render_authoritative_report(
    *,
    accepted: list[dict[str, Any]],
    verifications: list[dict[str, Any]],
    coverage: dict[str, Any],
    uncertainty: str,
) -> str:
    lines = ["# Adaptive staged repository assessment", "", "## Accepted findings", ""]
    if not accepted:
        lines.append("No critic-accepted findings.")
    for index, record in enumerate(accepted, 1):
        finding = record["verification"]
        lines.extend(
            [
                f"### {index}. {finding['claim']}",
                "",
                f"- Symbols: {finding['symbols']}",
                f"- Expected behavior: {finding['expected_behavior']}",
                f"- Expected-behavior source: {finding['expected_behavior_source']}",
                f"- Impact: {finding['impact']}",
                f"- Contract evidence: {finding['contract_quote']}",
                f"- Behavior evidence: {finding['behavior_quote']}",
                f"- Disconfirmation: {finding['disconfirmation_quote']}",
                f"- Remediation: {finding['remediation']}",
                "",
            ]
        )
    lines.extend(["## Verification dispositions", ""])
    if not verifications:
        lines.append("No hypotheses were promoted.")
    for item in verifications:
        lines.append(
            f"- `{item['scope']}`: {item.get('decision', 'no_result')} — {item.get('claim', '')}"
        )
    lines.extend(
        [
            "",
            "## Coverage and uncertainty",
            "",
            f"- Substantive package coverage: {coverage['covered']}/{len(PACKAGE_NAMES)}.",
            f"- Controller-assigned uncertainty: {uncertainty}.",
            "",
        ]
    )
    return "\n".join(lines)


def _coverage_snapshot(traces: list[StageTrace]) -> dict[str, Any]:
    by_scope: dict[str, list[dict[str, Any]]] = {scope: [] for scope in PACKAGE_NAMES}
    for trace in traces:
        for call in trace.calls:
            by_scope[trace.scope].append(
                {"command": call["command"], "result": call["result"], "stage": trace.stage_id}
            )
    scopes: dict[str, Any] = {}
    for scope, calls in by_scope.items():
        legacy_trace = v1.ScopeTrace(scope=scope, commands=calls)
        scopes[scope] = legacy_trace.coverage()
    return {"covered": sum(item["covered"] for item in scopes.values()), "scopes": scopes}


def run_adaptive_assessment(
    *,
    engine: ToolEngine,
    seed: int,
    root: Path,
    venv: Path,
    rg_path: Path,
    output_dir: Path,
    fingerprint: dict[str, Any],
    environment_validation: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=False, exist_ok=False)
    dossier_dir = output_dir / "dossiers"
    dossier_dir.mkdir()
    transcript = output_dir / "transcript.jsonl"
    report_path = output_dir / "raw-controller-report.md"
    metadata_path = output_dir / "run-metadata.json"
    started_at = base.utc_now()
    usage = v1.UsageTotal()
    protocol_violations: list[str] = []
    total_shell_calls = [0]
    order = list(PACKAGE_NAMES)
    random.Random(seed).shuffle(order)

    dossiers: dict[str, dict[str, Any]] = {}
    dossier_hashes: dict[str, str] = {}
    for scope in PACKAGE_NAMES:
        dossier = build_package_dossier(root, scope)
        dossiers[scope] = dossier
        dossier_bytes = canonical_dossier_bytes(dossier)
        (dossier_dir / f"{scope}.json").write_bytes(dossier_bytes)
        dossier_hashes[scope] = base.sha256_bytes(dossier_bytes)

    selections: list[dict[str, Any]] = []
    scout_results: list[dict[str, Any]] = []
    traces: list[StageTrace] = []
    for scope in order:
        selection, first_attempt = run_selection(
            engine=engine,
            seed=seed,
            scope=scope,
            dossier=dossiers[scope],
            transcript=transcript,
            usage=usage,
            protocol_violations=protocol_violations,
        )
        if selection is None:
            selections.append({"scope": scope, "status": "no_valid_hypothesis"})
            scout_results.append({"scope": scope, "disposition": "no_valid_hypothesis"})
            continue
        selections.append(
            {"scope": scope, "status": "accepted", "first_attempt": first_attempt, **selection}
        )
        result, natural, trace = run_empirical_stage(
            engine=engine,
            seed=seed,
            stage="scout",
            scope=scope,
            stage_id=f"scout:{scope}",
            system_prompt=SCOUT_SYSTEM_PROMPT,
            user_payload={"dossier_slice": focused_dossier(dossiers[scope], selection)},
            selection=selection,
            report_tool=HYPOTHESIS_RESULT_TOOL,
            shell_budget=SCOUT_SHELL_BUDGET,
            root=root,
            venv=venv,
            rg_path=rg_path,
            transcript=transcript,
            usage=usage,
            total_shell_calls=total_shell_calls,
            protocol_violations=protocol_violations,
        )
        traces.append(trace)
        if result:
            result["structured_before_forcing"] = natural
            scout_results.append(result)
        else:
            scout_results.append({"scope": scope, "disposition": "no_result"})

    promoted = promote_hypotheses(scout_results, order)
    verifications: list[dict[str, Any]] = []
    for index, hypothesis in enumerate(promoted, 1):
        scope = hypothesis["scope"]
        selection = hypothesis["selection"]
        result, natural, trace = run_empirical_stage(
            engine=engine,
            seed=seed,
            stage="verifier",
            scope=scope,
            stage_id=f"verifier:{index}:{scope}",
            system_prompt=VERIFIER_SYSTEM_PROMPT,
            user_payload={
                "dossier_slice": focused_dossier(dossiers[scope], selection),
                "validated_scout_hypothesis": hypothesis,
            },
            selection=selection,
            report_tool=VERIFICATION_TOOL,
            shell_budget=VERIFIER_SHELL_BUDGET,
            root=root,
            venv=venv,
            rg_path=rg_path,
            transcript=transcript,
            usage=usage,
            total_shell_calls=total_shell_calls,
            protocol_violations=protocol_violations,
        )
        traces.append(trace)
        if result:
            result["structured_before_forcing"] = natural
            verifications.append(result)
        else:
            verifications.append(
                {"scope": scope, "decision": "no_result", "hypothesis": hypothesis}
            )

    critic_records: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for index, verification in enumerate(verifications, 1):
        if verification.get("decision") != "confirmed":
            continue
        decision, response = base.run_critic(engine, _critic_payload(verification), seed)
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

    coverage = _coverage_snapshot(traces)
    uncertainty = v1.controller_uncertainty(coverage["covered"])
    report = render_authoritative_report(
        accepted=accepted,
        verifications=verifications,
        coverage=coverage,
        uncertainty=uncertainty,
    )
    report_path.write_text(report, encoding="utf-8")
    distribution = {scope: 0 for scope in PACKAGE_NAMES}
    for trace in traces:
        distribution[trace.scope] += len(trace.calls)
    max_calls = max(distribution.values(), default=0)
    valid_selections = sum(item.get("status") == "accepted" for item in selections)
    structured_scouts = sum(
        item.get("disposition") in {"supported", "unresolved", "disproved"}
        for item in scout_results
    )
    structured_verifiers = sum(
        item.get("decision") in {"confirmed", "rejected", "insufficient_evidence"}
        for item in verifications
    )
    complete = (
        valid_selections == len(PACKAGE_NAMES)
        and structured_scouts == len(PACKAGE_NAMES)
        and structured_verifiers == len(promoted)
    )
    metadata = {
        "schema": RUN_SCHEMA,
        "condition": CONDITION,
        "seed": seed,
        "started_at": started_at,
        "finished_at": base.utc_now(),
        "target_commit": TARGET_COMMIT,
        "target_archive_sha256": TARGET_ARCHIVE_SHA256,
        "model": fingerprint["model_metadata"].get("model_label"),
        "fingerprint": fingerprint,
        "base_url_retained": False,
        "thinking": False,
        "temperature": 0,
        "budgets": {
            "shell_call_ceiling": SHELL_CALL_CEILING,
            "scout_calls_per_scope": SCOUT_SHELL_BUDGET,
            "scout_call_maximum": SCOUT_SHELL_BUDGET * len(PACKAGE_NAMES),
            "verifier_calls_per_hypothesis": VERIFIER_SHELL_BUDGET,
            "verifier_call_maximum": VERIFIER_SHELL_BUDGET * MAX_PROMOTED_HYPOTHESES,
        },
        "shell_tool_calls": total_shell_calls[0],
        "shell_call_cap_bound": total_shell_calls[0] == SHELL_CALL_CEILING,
        "scope_call_distribution": distribution,
        "max_scope_concentration": (
            max_calls / total_shell_calls[0] if total_shell_calls[0] else 0.0
        ),
        "scope_order": order,
        "dossiers": {"schema": DOSSIER_SCHEMA, "sha256": dossier_hashes},
        "selections": {"valid": valid_selections, "records": selections},
        "scouts": {"structured": structured_scouts, "results": scout_results},
        "promotion": {
            "rule": "supported then unresolved; seeded scope order; first three",
            "selected": len(promoted),
            "records": promoted,
        },
        "verifiers": {"structured": structured_verifiers, "results": verifications},
        "critic": {"calls": len(critic_records), "records": critic_records},
        "accepted_findings": accepted,
        "substantive_coverage": coverage,
        "remaining_uncertainty": uncertainty,
        "authoritative_report": "deterministic_controller_renderer",
        "completion_mode": "structured" if complete else "incomplete",
        "lifecycle": "final" if complete else "aborted",
        "usage": usage.snapshot(),
        "protocol_violations": protocol_violations,
        "prompt_sha256": {
            "selection": base.sha256_bytes(SELECTION_SYSTEM_PROMPT.encode("utf-8")),
            "scout": base.sha256_bytes(SCOUT_SYSTEM_PROMPT.encode("utf-8")),
            "verifier": base.sha256_bytes(VERIFIER_SYSTEM_PROMPT.encode("utf-8")),
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
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(f"refusing to overwrite {args.output_dir}")
    if not args.root.is_dir() or not args.venv.is_dir() or not args.rg.is_file():
        parser.error("root, venv, or rg path is invalid")
    fingerprint = base._load_fingerprint(args.fingerprint)
    environment_validation = v1.validate_sanitized_sandbox(args.root, args.venv, args.rg)
    if not environment_validation["valid"]:
        args.output_dir.mkdir(parents=False, exist_ok=False)
        invalid = {
            "schema": RUN_SCHEMA,
            "condition": CONDITION,
            "seed": args.seed,
            "lifecycle": "aborted",
            "validity": "invalid",
            "invalid_reason": "sanitized sandbox validation failed before model execution",
            "target_commit": TARGET_COMMIT,
            "target_archive_sha256": TARGET_ARCHIVE_SHA256,
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
    metadata = run_adaptive_assessment(
        engine=engine,
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
