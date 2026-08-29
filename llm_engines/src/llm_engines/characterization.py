"""Synthetic, privacy-bounded probes for an LLM engine endpoint.

The probes measure observable interface behavior. They do not infer hidden
reasoning, model internals, or general task quality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import argparse
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
    LogprobModel,
    ToolCallingModel,
    ToolParameterSchema,
    ToolSpec,
)


CHARACTERIZATION_SCHEMA_VERSION = 2
CHARACTERIZATION_PROFILE = "llm_engines.model_characterization"
CHARACTERIZATION_CAMPAIGN_PROFILE = "llm_engines.model_characterization_campaign"
ProbeStatus = Literal["passed", "failed", "not_declared", "error"]


@dataclass(frozen=True)
class ProbeResult:
    """One probe outcome without prompt or response text."""

    probe_id: str
    status: ProbeStatus
    observations: dict[str, bool | int | float | str | None]
    error_type: str | None = None


@dataclass(frozen=True)
class CharacterizationReport:
    """Privacy-safe summary of a fixed synthetic probe suite."""

    schema_version: int
    suite: str
    suite_version: int
    started_at: str
    finished_at: str
    backend: str
    model_label: str
    thinking_requested: bool | None
    declared_capabilities: dict[str, Any]
    probes: tuple[ProbeResult, ...]
    interpretation_limit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class CharacterizationCampaignReport:
    """Repeated probe runs with bounded stability and latency summaries."""

    schema_version: int
    suite: str
    suite_version: int
    started_at: str
    finished_at: str
    backend: str
    model_label: str
    repetitions: int
    thinking_requested: bool | None
    runs: tuple[CharacterizationReport, ...]
    probe_aggregates: dict[str, dict[str, Any]]
    interpretation_limit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def summary_json(self) -> str:
        """Render campaign aggregates for the console without repeating every run."""

        payload = self.to_dict()
        payload.pop("runs", None)
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_model_label(label: str) -> str:
    """Remove host-specific path components from a provider model label."""

    return Path(label).name if Path(label).is_absolute() else label


def _probe_chat(
    engine: Any, *, thinking: bool | None
) -> tuple[ProbeResult, str, str]:
    expected = "CHARACTERIZATION_OK"
    response = engine.generate(
        GenerationRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content=f"Reply with exactly {expected} and no other text.",
                )
            ],
            temperature=0,
            max_tokens=512 if thinking is not False else 32,
            thinking=thinking,
        )
    )
    actual = response.text.strip()
    result = ProbeResult(
        probe_id="chat_exact_text",
        status="passed" if actual == expected else "failed",
        observations={
            "exact_match": actual == expected,
            "response_characters": len(response.text),
            "finish_reason": response.finish_reason,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "latency_ms": response.usage.latency_ms,
        },
    )
    return result, response.backend, _safe_model_label(response.model_name)


def _probe_structured(engine: Any, *, thinking: bool | None) -> ProbeResult:
    schema = {
        "type": "object",
        "properties": {"code": {"type": "integer", "const": 7}},
        "required": ["code"],
        "additionalProperties": False,
    }
    response = engine.generate(
        GenerationRequest(
            messages=[ChatMessage(role="user", content="Return the required object.")],
            temperature=0,
            max_tokens=512 if thinking is not False else 64,
            thinking=thinking,
            json_schema=schema,
        )
    )
    try:
        decoded = json.loads(response.text)
    except (TypeError, json.JSONDecodeError):
        decoded = None
    valid = decoded == {"code": 7}
    return ProbeResult(
        probe_id="structured_output",
        status="passed" if valid else "failed",
        observations={"schema_match": valid, "response_characters": len(response.text)},
    )


def _probe_tools(engine: Any, *, thinking: bool | None) -> ProbeResult:
    spec = ToolSpec(
        name="lookup_characterization_code",
        description="Return the supplied synthetic characterization code.",
        parameters={
            "code": ToolParameterSchema(type="string", description="Synthetic code")
        },
        required_params=["code"],
    )
    response = engine.generate_with_tools(
        GenerationRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content=(
                        "Call lookup_characterization_code once with code CHAR-7. "
                        "Do not answer directly."
                    ),
                )
            ],
            temperature=0,
            max_tokens=512 if thinking is not False else 128,
            thinking=thinking,
        ),
        [spec],
    )
    calls = response.message.tool_calls
    valid = (
        len(calls) == 1
        and calls[0].name == spec.name
        and calls[0].arguments == {"code": "CHAR-7"}
    )
    return ProbeResult(
        probe_id="tool_call",
        status="passed" if valid else "failed",
        observations={
            "valid_call": valid,
            "tool_call_count": len(calls),
            "finish_reason": response.finish_reason,
        },
    )


def _probe_logprobs(engine: Any, *, thinking: bool | None) -> ProbeResult:
    result = engine.generate_with_logprobs(
        GenerationRequest(
            messages=[ChatMessage(role="user", content="Reply with exactly SIGNAL.")],
            temperature=0,
            max_tokens=512 if thinking is not False else 16,
            thinking=thinking,
        )
    )
    valid = result.token_count > 0
    return ProbeResult(
        probe_id="token_logprobs",
        status="passed" if valid else "failed",
        observations={
            "token_count": result.token_count,
            "mean_logprob": result.mean_logprob if valid else None,
            "perplexity": result.perplexity if valid else None,
        },
    )


def characterize_engine(
    engine: Any, *, thinking: bool | None = None
) -> CharacterizationReport:
    """Run fixed synthetic probes and return a summary without raw content."""

    started = _now()
    capabilities = engine.get_capabilities()
    probes: list[ProbeResult] = []
    backend = type(engine).__name__
    model_label = "unreported"

    try:
        chat, backend, model_label = _probe_chat(engine, thinking=thinking)
        probes.append(chat)
    except Exception as exc:  # a probe failure must not suppress the report
        probes.append(ProbeResult("chat_exact_text", "error", {}, type(exc).__name__))

    optional = (
        ("structured_output", capabilities.structured_output, _probe_structured),
        (
            "tool_call",
            capabilities.tool_calling and isinstance(engine, ToolCallingModel),
            _probe_tools,
        ),
        (
            "token_logprobs",
            capabilities.logprobs and isinstance(engine, LogprobModel),
            _probe_logprobs,
        ),
    )
    for probe_id, supported, probe in optional:
        if not supported:
            probes.append(ProbeResult(probe_id, "not_declared", {}))
            continue
        try:
            probes.append(probe(engine, thinking=thinking))
        except Exception as exc:  # report the public exception type, not sensitive text
            probes.append(ProbeResult(probe_id, "error", {}, type(exc).__name__))

    return CharacterizationReport(
        schema_version=CHARACTERIZATION_SCHEMA_VERSION,
        suite=CHARACTERIZATION_PROFILE,
        suite_version=2,
        started_at=started,
        finished_at=_now(),
        backend=backend,
        model_label=model_label,
        thinking_requested=thinking,
        declared_capabilities=capabilities.model_dump(),
        probes=tuple(probes),
        interpretation_limit=(
            "Measures this endpoint's observable behavior on fixed synthetic probes; "
            "it does not reveal hidden reasoning or establish general task quality."
        ),
    )


def characterize_engine_repeated(
    engine: Any,
    *,
    repetitions: int,
    thinking: bool | None = None,
) -> CharacterizationCampaignReport:
    """Repeat the fixed suite and summarize observed status and chat latency."""

    if repetitions < 2:
        raise ValueError("repetitions must be at least 2 for a campaign")
    started = _now()
    runs = tuple(
        characterize_engine(engine, thinking=thinking) for _ in range(repetitions)
    )
    probe_ids = sorted({probe.probe_id for run in runs for probe in run.probes})
    aggregates: dict[str, dict[str, Any]] = {}
    for probe_id in probe_ids:
        results = [
            probe
            for run in runs
            for probe in run.probes
            if probe.probe_id == probe_id
        ]
        statuses = [probe.status for probe in results]
        counts = {status: statuses.count(status) for status in sorted(set(statuses))}
        aggregate: dict[str, Any] = {
            "runs": len(results),
            "status_counts": counts,
            "status_stable": len(set(statuses)) == 1,
            "pass_rate": statuses.count("passed") / len(statuses),
        }
        latencies = [
            float(value)
            for result in results
            if isinstance((value := result.observations.get("latency_ms")), (int, float))
        ]
        if latencies:
            aggregate["latency_ms"] = {
                "samples": len(latencies),
                "minimum": min(latencies),
                "median": statistics.median(latencies),
                "maximum": max(latencies),
            }
        aggregates[probe_id] = aggregate
    return CharacterizationCampaignReport(
        schema_version=CHARACTERIZATION_SCHEMA_VERSION,
        suite=CHARACTERIZATION_CAMPAIGN_PROFILE,
        suite_version=2,
        started_at=started,
        finished_at=_now(),
        backend=runs[-1].backend,
        model_label=runs[-1].model_label,
        repetitions=repetitions,
        thinking_requested=thinking,
        runs=runs,
        probe_aggregates=aggregates,
        interpretation_limit=(
            "Measures repeatability of fixed synthetic probes during this campaign; "
            "it does not establish reliability on real tasks or identify causes of variation."
        ),
    )


def build_characterization_artifact(
    report: CharacterizationReport | CharacterizationCampaignReport,
) -> RunArtifact:
    """Wrap a characterization report in the shared durable experiment envelope."""

    body = report.to_dict()
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    time = TimeDeclaration(
        execution_started_at=TimeValue(status="value", value=report.started_at, source="runner"),
        execution_finished_at=TimeValue(status="value", value=report.finished_at, source="runner"),
        artifact_created_at=TimeValue(status="value", value=report.finished_at, source="runner"),
    )
    envelope = RecordEnvelope(
        kind="experiment",
        envelope_schema_version=1,
        body_version=1,
        profile=report.suite,
        profile_version=report.suite_version,
        record_id=f"mc_{digest[:32]}",
        lifecycle="final",
        relationships=(),
        attachments=(),
        actors=(
            Actor(
                actor_id="characterization-runner",
                role="recorder",
                name="llm_engines.characterization",
                version="1",
            ),
        ),
        time=time,
        privacy=PrivacyDeclaration(
            declared_content_categories=("synthetic_prompt", "model_configuration"),
            body_bytes_sensitivity="low; raw prompts and model responses are not retained",
            transformations_applied=(
                {"operation": "omit_raw_probe_content", "version": "1"},
                {"operation": "omit_exception_messages", "version": "1"},
                {"operation": "model_label_basename_only", "version": "1"},
            ),
            validation=PrivacyValidation(
                status="validated",
                scope=("artifact body contains no raw prompt, response, or exception message",),
                validator="llm_engines.characterization",
                policy_id="synthetic-probes-no-raw-content",
                policy_version="1",
                validated_at=report.finished_at,
            ),
        ),
        omissions=(),
        capabilities=(
            CapabilityClaim(
                operation="model_characterization",
                requirements=(
                    CapabilityRequirement(type="external_service", ref="model_endpoint"),
                    CapabilityRequirement(type="implementation", ref=report.suite),
                ),
                execution_mode="live_external",
                effect_class="read_only",
                determinism=DeterminismClaim(
                    claim="best_effort",
                    evidence_basis="exercised",
                    conditions=("temperature=0", "fixed synthetic prompts"),
                ),
                implementation_version="2",
            ),
        ),
        execution_environment={"backend": report.backend, "model_label": report.model_label},
    )
    return RunArtifact(envelope=envelope, body=body)


def main(argv: list[str] | None = None) -> int:
    """Run the suite from a configured engine or direct backend arguments."""

    parser = argparse.ArgumentParser(
        prog="llm-characterize",
        description="Measure observable endpoint behavior with fixed synthetic probes.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--engine-name", help="Named engine in an ai_tools YAML config")
    source.add_argument("--backend", help="Direct backend name, such as openai or ollama")
    parser.add_argument("--config", type=Path, help="YAML config used with --engine-name")
    parser.add_argument("--model", help="Model label used with --backend")
    parser.add_argument("--base-url", help="Endpoint URL used with --backend")
    parser.add_argument(
        "--api-key-env",
        help="Environment variable containing the API key; its value is never recorded",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Treat a direct OpenAI backend as cloud-hosted (default: local-compatible)",
    )
    parser.add_argument("--artifact", type=Path, help="Write a durable experiment artifact")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of complete suite repetitions (default: 1)",
    )
    parser.add_argument(
        "--thinking",
        choices=("default", "off", "on"),
        default="default",
        help="Preserve server default, suppress thinking, or request thinking",
    )
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

    if args.runs < 1:
        parser.error("--runs must be at least 1")
    thinking = {"default": None, "off": False, "on": True}[args.thinking]
    report: CharacterizationReport | CharacterizationCampaignReport
    report = (
        characterize_engine(engine, thinking=thinking)
        if args.runs == 1
        else characterize_engine_repeated(
            engine, repetitions=args.runs, thinking=thinking
        )
    )
    if isinstance(report, CharacterizationCampaignReport):
        sys.stdout.write(report.summary_json())
    else:
        sys.stdout.write(report.to_json())
    if args.artifact:
        dump_artifact(build_characterization_artifact(report), args.artifact)
        print(f"Wrote privacy-bounded artifact: {args.artifact}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
