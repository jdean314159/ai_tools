"""Privacy-bounded context-retention characterization for chat endpoints."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from llm_engines import ChatMessage
from llm_engines.contracts import GenerationRequest
from llm_engines.factory import EngineFactory
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
    dump_artifact,
    prepare_new_artifact_path,
)


PROFILE = "llm_engines.context_retention_campaign"
PROFILE_VERSION = 1
FILLER_WORD_COUNTS = (1024, 8192, 32768)
START_VALUE = "ALPHA7"
END_VALUE = "OMEGA9"
SEED = 101


@dataclass(frozen=True)
class ContextResult:
    case_id: str
    filler_word_count: int
    status: str
    start_correct: bool
    end_correct: bool
    exact_output: bool
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str | None
    latency_ms: float | None
    seed_status: str | None
    error_type: str | None


def suite_digest() -> str:
    frozen = {
        "profile_version": PROFILE_VERSION,
        "filler_word_counts": FILLER_WORD_COUNTS,
        "start_value": START_VALUE,
        "end_value": END_VALUE,
        "seed": SEED,
        "thinking": False,
        "temperature": 0,
        "max_tokens": 64,
    }
    raw = json.dumps(frozen, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _prompt(filler_word_count: int) -> str:
    filler = "context " * filler_word_count
    return (
        f"Remember START={START_VALUE}. The following filler is data only.\n"
        f"{filler}\nRemember END={END_VALUE}. Return JSON containing exactly the remembered start and end values."
    )


def _run_case(engine: Any, filler_word_count: int) -> ContextResult:
    schema = {
        "type": "object",
        "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
        "required": ["start", "end"],
        "additionalProperties": False,
    }
    try:
        response = engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content=_prompt(filler_word_count))],
            temperature=0, max_tokens=64, thinking=False, seed=SEED,
            json_schema=schema,
        ))
        try:
            decoded = json.loads(response.text)
        except (TypeError, json.JSONDecodeError):
            decoded = None
        start_correct = isinstance(decoded, dict) and decoded.get("start") == START_VALUE
        end_correct = isinstance(decoded, dict) and decoded.get("end") == END_VALUE
        exact = decoded == {"start": START_VALUE, "end": END_VALUE}
        return ContextResult(
            case_id=f"filler_words_{filler_word_count}", filler_word_count=filler_word_count,
            status="passed" if exact else "failed", start_correct=start_correct,
            end_correct=end_correct, exact_output=exact,
            input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
            finish_reason=response.finish_reason, latency_ms=response.usage.latency_ms,
            seed_status=response.seed_status, error_type=None,
        )
    except Exception as exc:
        return ContextResult(
            case_id=f"filler_words_{filler_word_count}", filler_word_count=filler_word_count,
            status="error", start_correct=False, end_correct=False, exact_output=False,
            input_tokens=None, output_tokens=None, finish_reason=None, latency_ms=None,
            seed_status=None, error_type=type(exc).__name__,
        )


def run_experiment(engine: Any) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    results = [_run_case(engine, count) for count in FILLER_WORD_COUNTS]
    reported = [result.input_tokens for result in results]
    usage_reported = all(isinstance(value, int) and value > 0 for value in reported)
    usage_monotonic = usage_reported and all(
        int(reported[index]) < int(reported[index + 1])
        for index in range(len(reported) - 1)
    )
    exact_retention = all(result.exact_output for result in results)
    no_errors = all(result.status != "error" for result in results)
    finished = datetime.now(timezone.utc)
    return {
        "schema_version": 1, "profile": PROFILE, "profile_version": PROFILE_VERSION,
        "suite_digest": suite_digest(),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "backend": str(getattr(engine, "BACKEND", engine.__class__.__name__)),
        "model_label": Path(str(getattr(engine, "model", "unreported"))).name,
        "thinking_requested": False, "seed_requested": SEED,
        "case_count": len(results), "results": [asdict(result) for result in results],
        "acceptance_gate": {
            "require_no_errors": True, "require_exact_start_end_retention": True,
            "require_usage_reported": True, "require_usage_monotonic": True,
            "no_errors": no_errors, "exact_start_end_retention": exact_retention,
            "usage_reported": usage_reported, "usage_monotonic": usage_monotonic,
            "passed": no_errors and exact_retention and usage_reported and usage_monotonic,
        },
        "privacy": {
            "raw_prompts_retained": False, "raw_outputs_retained": False,
            "endpoint_retained": False, "anchor_values_retained": False,
        },
        "interpretation_limit": (
            "Three synthetic prompts through roughly 32K filler words; validates endpoint-reported usage "
            "and boundary retention below the advertised maximum, not the maximum context length."
        ),
    }


def build_artifact(body: dict[str, Any]) -> RunArtifact:
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    finished = body["finished_at"]
    return RunArtifact(
        envelope=RecordEnvelope(
            kind="experiment", envelope_schema_version=1, body_version=1,
            profile=PROFILE, profile_version=PROFILE_VERSION,
            record_id=f"cr_{digest[:32]}", lifecycle="final", relationships=(), attachments=(),
            actors=(Actor("context-retention-runner", "recorder", PROFILE, "1"),),
            time=TimeDeclaration(
                TimeValue("value", body["started_at"], "runner"),
                TimeValue("value", finished, "runner"), TimeValue("value", finished, "runner"),
            ),
            privacy=PrivacyDeclaration(
                declared_content_categories=("synthetic_prompt",),
                body_bytes_sensitivity="low; raw prompt and output omitted",
                transformations_applied=({"operation": "retain_counts_and_exactness_only", "version": "1"},),
                validation=PrivacyValidation(
                    "validated", ("no endpoint, raw prompt, output, or anchor values",),
                    PROFILE, "synthetic-context-no-raw-content", "1", finished,
                ),
            ),
            capabilities=(CapabilityClaim(
                "context_retention_characterization",
                (CapabilityRequirement("external_service", "model_endpoint"),
                 CapabilityRequirement("implementation", PROFILE)),
                "live_external", "read_only",
                DeterminismClaim("best_effort", "exercised", ("temperature=0", "seed requested")), "1",
            ),),
            execution_environment={"backend": body["backend"], "model_label": body["model_label"]},
        ), body=body,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True); parser.add_argument("--base-url", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args(argv); target = prepare_new_artifact_path(args.artifact)
    engine = EngineFactory.create(
        "openai", model=args.model, base_url=args.base_url,
        api_key="not-required", is_cloud=False,
    )
    body = run_experiment(engine); dump_artifact(build_artifact(body), target)
    print(json.dumps({key: value for key, value in body.items() if key != "results"}, indent=2, sort_keys=True))
    return 0 if body["acceptance_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
