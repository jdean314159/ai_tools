"""Adapters from legacy agent evaluation records to the shared artifact envelope."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from llm_harness_core import (
    Actor,
    CapabilityClaim,
    CapabilityRequirement,
    DeterminismClaim,
    Omission,
    PrivacyDeclaration,
    PrivacyValidation,
    RecordEnvelope,
    Relationship,
    RunArtifact,
    TimeDeclaration,
    TimeValue,
)


ADAPTER_VERSION = "1"


def _canonical_source(record: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    copied = deepcopy(dict(record))
    encoded = json.dumps(copied, sort_keys=True, separators=(",", ":"), default=str).encode()
    return copied, hashlib.sha256(encoded).hexdigest()


def _identity(profile: str, digest: str) -> str:
    return f"rr_{uuid5(NAMESPACE_URL, f'ai_tools:{profile}:{ADAPTER_VERSION}:{digest}').hex}"


def _unknown_time() -> TimeDeclaration:
    return TimeDeclaration(
        execution_started_at=TimeValue(status="unknown"),
        execution_finished_at=TimeValue(status="unknown"),
        adapted_at=TimeValue(status="unknown", source="legacy adapter did not retain wall-clock adaptation time"),
    )


def _legacy_privacy(categories: tuple[str, ...]) -> PrivacyDeclaration:
    return PrivacyDeclaration(
        declared_content_categories=categories,
        body_bytes_sensitivity="unknown",
        validation=PrivacyValidation(status="not_validated"),
    )


def _base_envelope(
    *,
    profile: str,
    digest: str,
    privacy_categories: tuple[str, ...],
    omissions: tuple[Omission, ...],
    capabilities: tuple[CapabilityClaim, ...] = (),
    execution_environment: Mapping[str, Any] | None = None,
) -> RecordEnvelope:
    return RecordEnvelope(
        kind="agent_run",
        envelope_schema_version=1,
        body_version=1,
        profile=profile,
        profile_version=1,
        record_id=_identity(profile, digest),
        lifecycle="final",
        relationships=(
            Relationship(
                relation_type="derived_from",
                target_kind=f"legacy_agent_run.{profile}",
                target_id=f"sha256:{digest}",
            ),
        ),
        attachments=(),
        actors=(
            Actor(
                actor_id="adapter",
                role="adapter",
                name=f"agent_lib.{profile}_legacy_adapter",
                version=ADAPTER_VERSION,
            ),
        ),
        time=_unknown_time(),
        privacy=_legacy_privacy(privacy_categories),
        omissions=omissions,
        capabilities=capabilities,
        execution_environment=dict(execution_environment or {}),
    )


def adapt_nav_v1(record: Mapping[str, Any]) -> RunArtifact:
    """Adapt one NAV schema-v1 mapping without mutating or replacing it."""

    source, digest = _canonical_source(record)
    if source.get("schema_version") != 1 or not isinstance(source.get("run"), dict):
        raise ValueError("expected a NAV schema-v1 run record")
    run = dict(source["run"])
    steps = list(run.get("steps") or [])
    profile_data = {key: value for key, value in source.items() if key not in {"schema_version", "run", "score"}}
    profile_data["run_meta"] = run.get("meta") or {}
    body = {
        "task": {"task_id": "nav-test-00"},
        "status": run.get("status"),
        "stop_reason": run.get("stop_reason"),
        "elapsed_seconds": run.get("elapsed_seconds"),
        "step_count": run.get("step_count", len(steps)),
        "steps": steps,
        "final_output": run.get("final_output"),
        "model_roles": {"planner": (source.get("config") or {}).get("deployment", {})},
        "evaluation": source.get("score"),
        "profile_data": profile_data,
    }
    capabilities = (
        CapabilityClaim(
            operation="counterfactual_finalization",
            requirements=(
                CapabilityRequirement(type="body_path", ref="/steps"),
                CapabilityRequirement(type="body_path", ref="/profile_data/planner_usage"),
                CapabilityRequirement(type="configuration", ref="answer_key_and_question"),
                CapabilityRequirement(type="external_service", ref="model_service"),
                CapabilityRequirement(type="implementation", ref="nav_counterfactual_finalize"),
                CapabilityRequirement(type="configuration", ref="token_budget"),
            ),
            execution_mode="live_external",
            effect_class="unknown",
            determinism=DeterminismClaim(claim="not_claimed", evidence_basis="declared"),
            implementation_version="1",
        ),
    )
    environment = {"deployment": (source.get("config") or {}).get("deployment", {})}
    return RunArtifact(
        envelope=_base_envelope(
            profile="agent_lib.nav",
            digest=digest,
            privacy_categories=("prompt_or_task", "agent_trajectory", "tool_output", "filesystem_metadata"),
            omissions=(
                Omission(field_path="/time/execution_started_at", reason="absent_in_source_format"),
                Omission(field_path="/time/execution_finished_at", reason="absent_in_source_format"),
                Omission(field_path="/actors/original_producer", reason="absent_in_source_format"),
            ),
            capabilities=capabilities,
            execution_environment=environment,
        ),
        body=body,
    )


def restore_nav_v1(artifact: RunArtifact) -> dict[str, Any]:
    """Reconstruct the NAV-v1 mapping represented by the Phase 2 adapter."""

    if artifact.envelope.profile != "agent_lib.nav" or artifact.envelope.profile_version != 1:
        raise ValueError("expected an agent_lib.nav profile-v1 artifact")
    body = artifact.body
    profile_data = deepcopy(dict(body.get("profile_data") or {}))
    run_meta = profile_data.pop("run_meta", {})
    result = {"schema_version": 1, **profile_data}
    result["run"] = {
        "status": body.get("status"),
        "stop_reason": body.get("stop_reason"),
        "final_output": body.get("final_output"),
        "elapsed_seconds": body.get("elapsed_seconds"),
        "step_count": body.get("step_count"),
        "steps": deepcopy(list(body.get("steps") or [])),
        "meta": run_meta,
    }
    result["score"] = deepcopy(body.get("evaluation"))
    return result


_ASC_EVALUATION_FIELDS = {
    "visible_pass",
    "held_out_pass",
    "held_out_detail",
    "visible_oracle",
    "classification",
    "input_special_casing",
    "tamper_attempts",
    "verbalized_gaming_intent",
}


def adapt_asc_record(record: Mapping[str, Any]) -> RunArtifact:
    """Adapt one completed ASC task record into the shared agent-run body."""

    source, digest = _canonical_source(record)
    required = {"task_id", "mode", "seed", "status"}
    if not required.issubset(source):
        raise ValueError(f"ASC record missing required fields: {sorted(required - source.keys())}")
    step_observations = list(source.get("step_observations") or [])
    common_keys = {
        "task_id", "status", "stop_reason", "elapsed_seconds", "steps",
        "step_observations", "reasoning_trace", "worker", "mentor",
        *_ASC_EVALUATION_FIELDS,
    }
    profile_data = {key: value for key, value in source.items() if key not in common_keys}
    body = {
        "task": {"task_id": source["task_id"], "tier": source.get("tier")},
        "status": source.get("status"),
        "stop_reason": source.get("stop_reason"),
        "elapsed_seconds": source.get("elapsed_seconds"),
        "step_count": source.get("steps", len(step_observations)),
        "steps": step_observations,
        "final_output": None,
        "model_roles": {"worker": source.get("worker"), "mentor": source.get("mentor")},
        "evaluation": {key: source.get(key) for key in _ASC_EVALUATION_FIELDS if key in source},
        "profile_data": {
            **profile_data,
            "reasoning_trace": source.get("reasoning_trace") or [],
        },
    }
    worker = source.get("worker") if isinstance(source.get("worker"), dict) else {}
    return RunArtifact(
        envelope=_base_envelope(
            profile="agent_lib.asc",
            digest=digest,
            privacy_categories=("agent_reasoning", "tool_output", "evaluation_detail", "filesystem_metadata"),
            omissions=(
                Omission(field_path="/time/execution_started_at", reason="absent_in_source_format"),
                Omission(field_path="/time/execution_finished_at", reason="absent_in_source_format"),
                Omission(field_path="/final_output", reason="absent_in_source_format"),
                Omission(field_path="/actors/original_producer", reason="absent_in_source_format"),
            ),
            execution_environment={"backend": worker.get("backend"), "model": worker.get("model")},
        ),
        body=body,
    )


def restore_asc_record(artifact: RunArtifact) -> dict[str, Any]:
    """Reconstruct the ASC mapping represented by the Phase 2 adapter."""

    if artifact.envelope.profile != "agent_lib.asc" or artifact.envelope.profile_version != 1:
        raise ValueError("expected an agent_lib.asc profile-v1 artifact")
    body = artifact.body
    task = dict(body.get("task") or {})
    model_roles = dict(body.get("model_roles") or {})
    evaluation = deepcopy(dict(body.get("evaluation") or {}))
    profile_data = deepcopy(dict(body.get("profile_data") or {}))
    reasoning_trace = profile_data.pop("reasoning_trace", [])
    result = {
        **profile_data,
        "task_id": task.get("task_id"),
        "tier": task.get("tier"),
        "worker": model_roles.get("worker"),
        "mentor": model_roles.get("mentor"),
        **evaluation,
        "steps": body.get("step_count"),
        "status": body.get("status"),
        "stop_reason": body.get("stop_reason"),
        "elapsed_seconds": body.get("elapsed_seconds"),
        "reasoning_trace": reasoning_trace,
        "step_observations": deepcopy(list(body.get("steps") or [])),
    }
    return result
