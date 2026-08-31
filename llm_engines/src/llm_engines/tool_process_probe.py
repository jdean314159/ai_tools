"""Controlled probes of observable model tool-selection behavior."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any, Literal

from llm_harness_core import (
    Actor,
    CapabilityClaim,
    CapabilityRequirement,
    DeterminismClaim,
    PrivacyDeclaration,
    PrivacyValidation,
    RecordEnvelope,
    RunArtifact,
    TimeDeclaration,
    TimeValue,
)

from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    ToolCallingModel,
    ToolParameterSchema,
    ToolSpec,
)


TOOL_PROCESS_PROFILE = "llm_engines.tool_decision_campaign"
TOOL_PROCESS_SCHEMA_VERSION = 2
CaseStatus = Literal["passed", "failed", "error"]


@dataclass(frozen=True)
class ToolDecisionCaseResult:
    case_id: str
    expected_action: Literal["call_tool", "answer_directly"]
    status: CaseStatus
    observed_action: Literal["call_tool", "answer_directly", "error"]
    expected_tool: str | None
    observed_tool: str | None
    call_count: int
    arguments_match: bool | None
    direct_answer_match: bool | None
    finish_reason: str | None
    latency_ms: float | None
    error_type: str | None = None


@dataclass(frozen=True)
class ToolDecisionCampaignReport:
    schema_version: int
    profile: str
    profile_version: int
    started_at: str
    finished_at: str
    backend: str
    model_label: str
    repetitions: int
    cases_per_run: int
    thinking_requested: bool | None
    results: tuple[ToolDecisionCaseResult, ...]
    case_aggregates: dict[str, dict[str, Any]]
    interpretation_limit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_json(self) -> str:
        payload = self.to_dict()
        payload.pop("results", None)
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class _Case:
    case_id: str
    prompt: str
    tools: tuple[ToolSpec, ...]
    expected_action: Literal["call_tool", "answer_directly"]
    expected_tool: str | None = None
    expected_arguments: dict[str, Any] | None = None
    expected_text: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_model_label(label: str) -> str:
    return Path(label).name if Path(label).is_absolute() else label


def _spec(name: str, description: str, parameters: dict[str, str]) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters={
            key: ToolParameterSchema(type=value, description=f"Synthetic {key}")
            for key, value in parameters.items()
        },
        required_params=list(parameters),
    )


def _cases() -> tuple[_Case, ...]:
    lookup = _spec(
        "lookup_record",
        "Look up one synthetic record by code.",
        {"code": "string"},
    )
    add = _spec(
        "add_numbers",
        "Add two integers when arithmetic must be performed by a tool.",
        {"left": "integer", "right": "integer"},
    )
    set_flag = _spec(
        "set_flag",
        "Set a synthetic flag and repeat count.",
        {"enabled": "boolean", "count": "integer"},
    )
    return (
        _Case(
            case_id="required_single_tool",
            prompt="Use lookup_record exactly once with code REC-17. Do not answer directly.",
            tools=(lookup,),
            expected_action="call_tool",
            expected_tool="lookup_record",
            expected_arguments={"code": "REC-17"},
        ),
        _Case(
            case_id="choose_relevant_tool",
            prompt="Use the appropriate tool to add 4 and 9. Do not answer directly.",
            tools=(lookup, add),
            expected_action="call_tool",
            expected_tool="add_numbers",
            expected_arguments={"left": 4, "right": 9},
        ),
        _Case(
            case_id="avoid_unnecessary_tool",
            prompt="Reply with exactly BLUE. Do not call a tool.",
            tools=(lookup, add),
            expected_action="answer_directly",
            expected_text="BLUE",
        ),
        _Case(
            case_id="typed_arguments",
            prompt="Call set_flag exactly once with enabled true and count 3.",
            tools=(set_flag,),
            expected_action="call_tool",
            expected_tool="set_flag",
            expected_arguments={"enabled": True, "count": 3},
        ),
    )


def _run_case(engine: Any, case: _Case, *, thinking: bool | None) -> ToolDecisionCaseResult:
    try:
        response = engine.generate_with_tools(
            GenerationRequest(
                messages=[ChatMessage(role="user", content=case.prompt)],
                max_tokens=128,
                temperature=0,
                thinking=thinking,
            ),
            list(case.tools),
        )
    except Exception as exc:
        return ToolDecisionCaseResult(
            case_id=case.case_id,
            expected_action=case.expected_action,
            status="error",
            observed_action="error",
            expected_tool=case.expected_tool,
            observed_tool=None,
            call_count=0,
            arguments_match=None,
            direct_answer_match=None,
            finish_reason=None,
            latency_ms=None,
            error_type=type(exc).__name__,
        )

    calls = response.message.tool_calls
    observed_action: Literal["call_tool", "answer_directly", "error"] = (
        "call_tool" if calls else "answer_directly"
    )
    observed_tool = calls[0].name if len(calls) == 1 else None
    arguments_match = (
        len(calls) == 1 and calls[0].arguments == case.expected_arguments
        if case.expected_action == "call_tool"
        else None
    )
    direct_match = (
        response.text.strip() == case.expected_text
        if case.expected_action == "answer_directly"
        else None
    )
    passed = (
        len(calls) == 1 and observed_tool == case.expected_tool and arguments_match is True
        if case.expected_action == "call_tool"
        else not calls and direct_match is True
    )
    return ToolDecisionCaseResult(
        case_id=case.case_id,
        expected_action=case.expected_action,
        status="passed" if passed else "failed",
        observed_action=observed_action,
        expected_tool=case.expected_tool,
        observed_tool=observed_tool,
        call_count=len(calls),
        arguments_match=arguments_match,
        direct_answer_match=direct_match,
        finish_reason=response.finish_reason,
        latency_ms=response.usage.latency_ms,
    )


def run_tool_decision_campaign(
    engine: Any,
    *,
    repetitions: int = 3,
    thinking: bool | None = None,
) -> ToolDecisionCampaignReport:
    """Measure repeatability of fixed tool-selection and argument decisions."""

    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    capabilities = engine.get_capabilities()
    if not capabilities.tool_calling or not isinstance(engine, ToolCallingModel):
        raise ValueError("engine does not declare and implement tool calling")
    started = _now()
    cases = _cases()
    results = tuple(
        _run_case(engine, case, thinking=thinking) for _ in range(repetitions) for case in cases
    )
    aggregates: dict[str, dict[str, Any]] = {}
    for case in cases:
        selected = [result for result in results if result.case_id == case.case_id]
        statuses = [result.status for result in selected]
        latencies = [result.latency_ms for result in selected if result.latency_ms is not None]
        aggregate: dict[str, Any] = {
            "runs": len(selected),
            "passed": statuses.count("passed"),
            "failed": statuses.count("failed"),
            "errors": statuses.count("error"),
            "pass_rate": statuses.count("passed") / len(statuses),
            "status_stable": len(set(statuses)) == 1,
        }
        if latencies:
            aggregate["latency_ms"] = {
                "samples": len(latencies),
                "minimum": min(latencies),
                "median": statistics.median(latencies),
                "maximum": max(latencies),
            }
        aggregates[case.case_id] = aggregate
    backend = getattr(
        engine,
        "BACKEND",
        engine.__class__.__module__.rsplit(".", 1)[-1],
    )
    model_label = _safe_model_label(str(getattr(engine, "model", "unreported")))
    return ToolDecisionCampaignReport(
        schema_version=TOOL_PROCESS_SCHEMA_VERSION,
        profile=TOOL_PROCESS_PROFILE,
        profile_version=2,
        started_at=started,
        finished_at=_now(),
        backend=str(backend),
        model_label=model_label,
        repetitions=repetitions,
        cases_per_run=len(cases),
        thinking_requested=thinking,
        results=results,
        case_aggregates=aggregates,
        interpretation_limit=(
            "Measures observable tool selection and argument construction on fixed synthetic "
            "cases; it does not reveal hidden reasoning or predict application reliability."
        ),
    )


def build_tool_decision_artifact(report: ToolDecisionCampaignReport) -> RunArtifact:
    body = report.to_dict()
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    time = TimeDeclaration(
        execution_started_at=TimeValue(status="value", value=report.started_at, source="runner"),
        execution_finished_at=TimeValue(status="value", value=report.finished_at, source="runner"),
        artifact_created_at=TimeValue(status="value", value=report.finished_at, source="runner"),
    )
    return RunArtifact(
        envelope=RecordEnvelope(
            kind="experiment",
            envelope_schema_version=1,
            body_version=1,
            profile=TOOL_PROCESS_PROFILE,
            profile_version=2,
            record_id=f"td_{digest[:32]}",
            lifecycle="final",
            relationships=(),
            attachments=(),
            actors=(
                Actor(
                    actor_id="tool-decision-runner",
                    role="recorder",
                    name="llm_engines.tool_process_probe",
                    version="1",
                ),
            ),
            time=time,
            privacy=PrivacyDeclaration(
                declared_content_categories=("synthetic_prompt", "model_configuration"),
                body_bytes_sensitivity="low; raw prompts and model responses are not retained",
                transformations_applied=(
                    {"operation": "omit_raw_case_content", "version": "1"},
                    {"operation": "omit_exception_messages", "version": "1"},
                    {"operation": "model_label_basename_only", "version": "1"},
                ),
                validation=PrivacyValidation(
                    status="validated",
                    scope=("body contains no raw prompt, response, or exception message",),
                    validator="llm_engines.tool_process_probe",
                    policy_id="synthetic-tool-decisions-no-raw-content",
                    policy_version="1",
                    validated_at=report.finished_at,
                ),
            ),
            capabilities=(
                CapabilityClaim(
                    operation="tool_decision_characterization",
                    requirements=(
                        CapabilityRequirement(type="external_service", ref="model_endpoint"),
                        CapabilityRequirement(type="implementation", ref=TOOL_PROCESS_PROFILE),
                    ),
                    execution_mode="live_external",
                    effect_class="read_only",
                    determinism=DeterminismClaim(
                        claim="best_effort",
                        evidence_basis="exercised",
                        conditions=(
                            "temperature=0",
                            "fixed synthetic prompts",
                            "tools not executed",
                        ),
                    ),
                    implementation_version="1",
                ),
            ),
            execution_environment={"backend": report.backend, "model_label": report.model_label},
        ),
        body=body,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="llm-tool-process-probe",
        description="Probe observable tool-selection behavior with synthetic cases.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--engine-name")
    source.add_argument("--backend")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--cloud", action="store_true")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--thinking",
        choices=("default", "off", "on"),
        default="default",
    )
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args(argv)

    from llm_harness_core import dump_artifact
    from llm_engines.factory import EngineFactory

    if args.engine_name:
        engine = EngineFactory.from_engine_name(args.engine_name, args.config)
    else:
        if not args.model:
            parser.error("--model is required with --backend")
        kwargs: dict[str, Any] = {"model": args.model}
        if args.base_url:
            kwargs["base_url"] = args.base_url
        if args.api_key_env:
            value = os.getenv(args.api_key_env)
            if not value:
                parser.error(f"environment variable {args.api_key_env!r} is empty or unset")
            kwargs["api_key"] = value
        if args.backend == "openai":
            kwargs.setdefault("api_key", "not-required")
            kwargs["is_cloud"] = args.cloud
        engine = EngineFactory.create(args.backend, **kwargs)

    report = run_tool_decision_campaign(
        engine,
        repetitions=args.runs,
        thinking={"default": None, "off": False, "on": True}[args.thinking],
    )
    sys.stdout.write(report.summary_json())
    if args.artifact:
        dump_artifact(build_tool_decision_artifact(report), args.artifact)
        print(f"Wrote privacy-bounded artifact: {args.artifact}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
