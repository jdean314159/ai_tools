"""Inspection and conservative comparison of durable run artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from llm_harness_core import (
    RunArtifact,
    SupportedBodyContract,
    body_support_status,
    load_artifact,
    summarize_artifact,
)


SUPPORTED_BODY_CONTRACTS = (
    SupportedBodyContract(kind="generation", body_version=1),
    SupportedBodyContract(
        kind="agent_run",
        body_version=1,
        profile="agent_lib.nav",
        profile_version=1,
    ),
    SupportedBodyContract(
        kind="agent_run",
        body_version=1,
        profile="agent_lib.asc",
        profile_version=1,
    ),
)


@dataclass(frozen=True)
class ArtifactInspection:
    common: Mapping[str, Any]
    body_support: str
    body_summary: Mapping[str, Any] | None
    notices: tuple[str, ...]


@dataclass(frozen=True)
class ArtifactComparison:
    left: ArtifactInspection
    right: ArtifactInspection
    common_facts: Mapping[str, Any]
    notices: tuple[str, ...]


def _common(artifact: RunArtifact) -> dict[str, Any]:
    envelope = artifact.envelope
    result = summarize_artifact(artifact)
    result.update(
        {
            "actors": [
                {
                    "actor_id": actor.actor_id,
                    "role": actor.role,
                    "name": actor.name,
                    "version": actor.version,
                }
                for actor in envelope.actors
            ],
            "relationships": [
                {
                    "relation_type": relationship.relation_type,
                    "target_kind": relationship.target_kind,
                    "target_id": relationship.target_id,
                }
                for relationship in envelope.relationships
            ],
            "privacy": {
                "declared_content_categories": list(
                    envelope.privacy.declared_content_categories
                ),
                "body_bytes_sensitivity": envelope.privacy.body_bytes_sensitivity,
                "validation_status": envelope.privacy.validation.status,
                "validation_scope": list(envelope.privacy.validation.scope),
            },
            "omissions": [
                {"field_path": omission.field_path, "reason": omission.reason}
                for omission in envelope.omissions
            ],
            "capabilities": [
                {
                    "operation": capability.operation,
                    "execution_mode": capability.execution_mode,
                    "effect_class": capability.effect_class,
                    "determinism": capability.determinism.claim,
                }
                for capability in envelope.capabilities
            ],
            "execution_environment": dict(envelope.execution_environment),
        }
    )
    return result


def _generation_summary(body: Mapping[str, Any]) -> dict[str, Any]:
    response = body.get("response") if isinstance(body.get("response"), Mapping) else {}
    model_identity = (
        body.get("model_identity")
        if isinstance(body.get("model_identity"), Mapping)
        else {}
    )
    usage = response.get("usage") if isinstance(response.get("usage"), Mapping) else {}
    message = response.get("message") if isinstance(response.get("message"), Mapping) else {}
    return {
        "record_type": "generation",
        "outcome": body.get("outcome"),
        "finish_reason": response.get("finish_reason"),
        "requested_model_label": model_identity.get("requested_label"),
        "reported_model_label": model_identity.get("reported_label"),
        "backend": model_identity.get("backend"),
        "usage": dict(usage),
        "response_has_content": bool(message.get("content")),
        "tool_call_count": len(message.get("tool_calls") or []),
        "structured_output_requested": bool(
            isinstance(body.get("request"), Mapping)
            and body["request"].get("json_schema") is not None
        ),
    }


def _agent_summary(artifact: RunArtifact) -> dict[str, Any]:
    body = artifact.body
    task = body.get("task") if isinstance(body.get("task"), Mapping) else {}
    evaluation = body.get("evaluation")
    return {
        "record_type": "agent_run",
        "profile": artifact.envelope.profile,
        "task_id": task.get("task_id"),
        "status": body.get("status"),
        "stop_reason": body.get("stop_reason"),
        "elapsed_seconds": body.get("elapsed_seconds"),
        "step_count": body.get("step_count"),
        "has_final_output": bool(body.get("final_output")),
        "has_evaluation": evaluation is not None,
        "model_roles": sorted((body.get("model_roles") or {}).keys()),
    }


def inspect_artifact(artifact: RunArtifact) -> ArtifactInspection:
    """Inspect common metadata and dispatch only supported body contracts."""

    support = body_support_status(artifact, SUPPORTED_BODY_CONTRACTS)
    common = _common(artifact)
    common["body_interpretation"] = support
    notices: list[str] = []
    if artifact.envelope.privacy.validation.status != "validated":
        notices.append("privacy declaration is not validated")
    if artifact.envelope.omissions:
        notices.append(f"artifact declares {len(artifact.envelope.omissions)} omitted fields")
    if support == "unsupported":
        notices.append(
            "body/profile version is unsupported; body-dependent privacy claims are unvalidated"
        )
        return ArtifactInspection(
            common=common,
            body_support=support,
            body_summary=None,
            notices=tuple(notices),
        )
    if artifact.envelope.kind == "generation":
        body_summary = _generation_summary(artifact.body)
    elif artifact.envelope.kind == "agent_run":
        body_summary = _agent_summary(artifact)
    else:  # guarded by SUPPORTED_BODY_CONTRACTS
        body_summary = None
    return ArtifactInspection(
        common=common,
        body_support=support,
        body_summary=body_summary,
        notices=tuple(notices),
    )


def inspect_artifact_file(path: str | Path) -> ArtifactInspection:
    return inspect_artifact(load_artifact(path))


def _model_labels(inspection: ArtifactInspection) -> dict[str, Any]:
    summary = inspection.body_summary or {}
    if summary.get("record_type") == "generation":
        return {
            "requested": summary.get("requested_model_label"),
            "reported": summary.get("reported_model_label"),
            "backend": summary.get("backend"),
        }
    return {"requested": None, "reported": None, "backend": None}


def compare_artifacts(left: RunArtifact, right: RunArtifact) -> ArtifactComparison:
    """Compare defensible common facts without claiming execution equivalence."""

    left_inspection = inspect_artifact(left)
    right_inspection = inspect_artifact(right)
    left_labels = _model_labels(left_inspection)
    right_labels = _model_labels(right_inspection)
    labels_comparable = (
        any(left_labels[key] is not None for key in ("requested", "reported"))
        and any(right_labels[key] is not None for key in ("requested", "reported"))
    )
    labels_equal = labels_comparable and left_labels == right_labels
    notices = [
        "model label equality is not model identity; digest, quantization, runtime, tokenizer, and template facts must be checked separately"
    ]
    if left_inspection.body_support == "unsupported" or right_inspection.body_support == "unsupported":
        notices.append("one or more bodies are unsupported; comparison is envelope-only")
    common_facts = {
        "same_kind": left.envelope.kind == right.envelope.kind,
        "same_body_contract": (
            left.envelope.kind,
            left.envelope.body_version,
            left.envelope.profile,
            left.envelope.profile_version,
        )
        == (
            right.envelope.kind,
            right.envelope.body_version,
            right.envelope.profile,
            right.envelope.profile_version,
        ),
        "same_lifecycle": left.envelope.lifecycle == right.envelope.lifecycle,
        "same_body_sensitivity_declaration": (
            left.envelope.privacy.body_bytes_sensitivity
            == right.envelope.privacy.body_bytes_sensitivity
        ),
        "model_labels_comparable": bool(labels_comparable),
        "model_labels_equal": bool(labels_equal),
        "model_identity_equal": "not_determined",
    }
    return ArtifactComparison(
        left=left_inspection,
        right=right_inspection,
        common_facts=common_facts,
        notices=tuple(notices),
    )


def compare_artifact_files(left: str | Path, right: str | Path) -> ArtifactComparison:
    return compare_artifacts(load_artifact(left), load_artifact(right))


def artifact_inspection_to_dict(inspection: ArtifactInspection) -> dict[str, Any]:
    return asdict(inspection)


def artifact_comparison_to_dict(comparison: ArtifactComparison) -> dict[str, Any]:
    return asdict(comparison)


def render_artifact_inspection(inspection: ArtifactInspection) -> str:
    common = inspection.common
    lines = [
        f"Artifact {common['record_id']}",
        f"  kind: {common['kind']}",
        f"  profile: {common.get('profile') or '-'}",
        f"  lifecycle: {common['lifecycle']}",
        f"  body support: {inspection.body_support}",
        f"  privacy: {common['privacy']['body_bytes_sensitivity']} ({common['privacy']['validation_status']})",
        f"  omissions: {len(common['omissions'])}",
    ]
    if inspection.body_summary is not None:
        lines.append("  body summary:")
        for key, value in inspection.body_summary.items():
            lines.append(f"    {key}: {json.dumps(value, sort_keys=True)}")
    for notice in inspection.notices:
        lines.append(f"  notice: {notice}")
    return "\n".join(lines)


def render_artifact_comparison(comparison: ArtifactComparison) -> str:
    lines = [
        "Artifact comparison",
        f"  left: {comparison.left.common['record_id']} ({comparison.left.common['kind']})",
        f"  right: {comparison.right.common['record_id']} ({comparison.right.common['kind']})",
    ]
    for key, value in comparison.common_facts.items():
        lines.append(f"  {key}: {json.dumps(value, sort_keys=True)}")
    for notice in comparison.notices:
        lines.append(f"  notice: {notice}")
    return "\n".join(lines)
