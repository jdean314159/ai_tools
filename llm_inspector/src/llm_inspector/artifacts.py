"""Inspection and conservative comparison of durable run artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from llm_harness_core import (
    ArtifactValidationError,
    AttachmentResolution,
    RunArtifact,
    SupportedBodyContract,
    body_support_status,
    load_artifact,
    load_artifact_bundle,
    summarize_artifact,
)


SUPPORTED_BODY_CONTRACTS = (
    SupportedBodyContract(kind="generation", body_version=1),
    SupportedBodyContract(
        kind="experiment",
        body_version=1,
        profile="agent_lib.asc_campaign",
        profile_version=1,
    ),
    SupportedBodyContract(
        kind="experiment",
        body_version=1,
        profile="agent_lib.nav_verifiable_campaign",
        profile_version=1,
    ),
    SupportedBodyContract(
        kind="experiment",
        body_version=1,
        profile="llm_engines.model_characterization",
        profile_version=2,
    ),
    SupportedBodyContract(
        kind="experiment",
        body_version=1,
        profile="llm_engines.model_characterization_campaign",
        profile_version=2,
    ),
    SupportedBodyContract(
        kind="experiment",
        body_version=1,
        profile="llm_engines.tool_decision_campaign",
        profile_version=2,
    ),
    SupportedBodyContract(
        kind="experiment",
        body_version=1,
        profile="llm_engines.tool_recovery_campaign",
        profile_version=2,
    ),
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
                "declared_content_categories": list(envelope.privacy.declared_content_categories),
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
        body.get("model_identity") if isinstance(body.get("model_identity"), Mapping) else {}
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
    evaluation_signals = {}
    if isinstance(evaluation, Mapping):
        for key in (
            "classification",
            "visible_pass",
            "held_out_pass",
            "input_special_casing",
        ):
            if key not in evaluation:
                continue
            value = evaluation[key]
            if isinstance(value, (str, bool, int, float)) or value is None:
                evaluation_signals[key] = value
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
        "evaluation_signals": evaluation_signals,
        "model_roles": sorted((body.get("model_roles") or {}).keys()),
    }


def _experiment_summary(artifact: RunArtifact) -> dict[str, Any]:
    body = artifact.body
    if artifact.envelope.profile == "llm_engines.tool_recovery_campaign":
        return {
            "record_type": "tool_recovery_campaign",
            "profile": artifact.envelope.profile,
            "suite_digest": body.get("suite_digest"),
            "backend": body.get("backend"),
            "model_label": body.get("model_label"),
            "repetitions": body.get("repetitions"),
            "cases_per_run": body.get("cases_per_run"),
            "thinking_requested": body.get("thinking_requested"),
            "seed_requested": body.get("seed_requested"),
            "condition_order": body.get("condition_order"),
            "primary_pass_rate": body.get("primary_pass_rate"),
            "fabricated_success_rate": body.get("fabricated_success_rate"),
            "baseline_headroom": body.get("baseline_headroom"),
            "interpretation_limit": body.get("interpretation_limit"),
        }
    if artifact.envelope.profile == "llm_engines.tool_decision_campaign":
        aggregates = (
            body.get("case_aggregates") if isinstance(body.get("case_aggregates"), Mapping) else {}
        )
        return {
            "record_type": "tool_decision_campaign",
            "profile": artifact.envelope.profile,
            "backend": body.get("backend"),
            "model_label": body.get("model_label"),
            "repetitions": body.get("repetitions"),
            "cases_per_run": body.get("cases_per_run"),
            "thinking_requested": body.get("thinking_requested"),
            "case_aggregates": dict(aggregates),
            "interpretation_limit": body.get("interpretation_limit"),
        }
    if artifact.envelope.profile == "llm_engines.model_characterization_campaign":
        aggregates = (
            body.get("probe_aggregates")
            if isinstance(body.get("probe_aggregates"), Mapping)
            else {}
        )
        return {
            "record_type": "model_characterization_campaign",
            "profile": artifact.envelope.profile,
            "backend": body.get("backend"),
            "model_label": body.get("model_label"),
            "thinking_requested": body.get("thinking_requested"),
            "repetitions": body.get("repetitions"),
            "probe_aggregates": dict(aggregates),
            "interpretation_limit": body.get("interpretation_limit"),
        }
    if artifact.envelope.profile == "llm_engines.model_characterization":
        probes = body.get("probes") if isinstance(body.get("probes"), list) else []
        status_counts: dict[str, int] = {}
        probe_statuses: dict[str, str] = {}
        for probe in probes:
            if not isinstance(probe, Mapping):
                continue
            probe_id = probe.get("probe_id")
            status = probe.get("status")
            if isinstance(status, str):
                status_counts[status] = status_counts.get(status, 0) + 1
                if isinstance(probe_id, str):
                    probe_statuses[probe_id] = status
        return {
            "record_type": "model_characterization",
            "profile": artifact.envelope.profile,
            "backend": body.get("backend"),
            "model_label": body.get("model_label"),
            "thinking_requested": body.get("thinking_requested"),
            "probe_count": len(probes),
            "status_counts": status_counts,
            "probe_statuses": probe_statuses,
            "interpretation_limit": body.get("interpretation_limit"),
        }
    campaign = body.get("campaign") if isinstance(body.get("campaign"), Mapping) else {}
    items = body.get("items") if isinstance(body.get("items"), list) else []
    aggregate = body.get("aggregate")
    decision = body.get("decision")
    aggregate_signals = {
        str(key): value
        for key, value in (aggregate.items() if isinstance(aggregate, Mapping) else ())
        if isinstance(value, (bool, int, float)) or value is None
    }
    decision_signals = {
        str(key): value
        for key, value in (decision.items() if isinstance(decision, Mapping) else ())
        if key in {"decision", "verdict", "status"}
        and (isinstance(value, (str, bool, int, float)) or value is None)
    }
    child_ids: set[str] = set()
    for relationship in artifact.envelope.relationships:
        if relationship.relation_type == "contains" and relationship.target_kind == "agent_run":
            child_ids.add(relationship.target_id)
    return {
        "record_type": "experiment",
        "profile": artifact.envelope.profile,
        "campaign_name": campaign.get("name"),
        "lifecycle": artifact.envelope.lifecycle,
        "item_count": len(items),
        "child_record_count": len(child_ids),
        "has_aggregate": isinstance(aggregate, Mapping),
        "has_decision": isinstance(decision, Mapping),
        "aggregate_signals": aggregate_signals,
        "decision_signals": decision_signals,
    }


def inspect_artifact(
    artifact: RunArtifact,
    *,
    attachment_resolutions: tuple[AttachmentResolution, ...] = (),
) -> ArtifactInspection:
    """Inspect common metadata and dispatch only supported body contracts."""

    support = body_support_status(artifact, SUPPORTED_BODY_CONTRACTS)
    common = _common(artifact)
    common["attachment_resolutions"] = [
        {
            "attachment_id": resolution.attachment_id,
            "status": resolution.status,
            "declared_inclusion": resolution.declared_inclusion,
            "requirement": resolution.requirement,
            "detail": resolution.detail,
        }
        for resolution in attachment_resolutions
    ]
    common["body_interpretation"] = support
    notices: list[str] = []
    if artifact.envelope.privacy.validation.status != "validated":
        notices.append("privacy declaration is not validated")
    if artifact.envelope.omissions:
        notices.append(f"artifact declares {len(artifact.envelope.omissions)} omitted fields")
    for resolution in attachment_resolutions:
        if resolution.status == "digest_mismatch":
            notices.append(f"attachment {resolution.attachment_id} has a digest mismatch")
        elif resolution.status == "unresolved" and resolution.declared_inclusion == "bundled":
            notices.append(f"bundled attachment {resolution.attachment_id} is unresolved")
        elif resolution.status == "unresolved" and resolution.requirement == "required":
            notices.append(f"required attachment {resolution.attachment_id} is detached")
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
    elif artifact.envelope.kind == "experiment":
        body_summary = _experiment_summary(artifact)
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


def inspect_artifact_path(path: str | Path) -> ArtifactInspection:
    """Inspect either an artifact JSON file or a portable bundle directory."""

    candidate = Path(path)
    if candidate.is_dir():
        bundle = load_artifact_bundle(candidate)
        inspection = inspect_artifact(
            bundle.artifact,
            attachment_resolutions=bundle.resolutions,
        )
        child_artifacts: list[dict[str, Any]] = []
        resolutions = {item.attachment_id: item for item in bundle.resolutions}
        for attachment in bundle.artifact.envelope.attachments:
            if attachment.logical_role != "child_run_artifact":
                continue
            resolution = resolutions.get(attachment.attachment_id)
            if (
                resolution is None
                or resolution.status != "resolved"
                or not resolution.resolved_path
            ):
                continue
            try:
                child = inspect_artifact(load_artifact(resolution.resolved_path))
            except (OSError, json.JSONDecodeError, ArtifactValidationError) as exc:
                child_artifacts.append(
                    {
                        "attachment_id": attachment.attachment_id,
                        "body_support": "invalid",
                        "error": str(exc),
                    }
                )
                continue
            child_artifacts.append(
                {
                    "record_id": child.common["record_id"],
                    "kind": child.common["kind"],
                    "profile": child.common.get("profile"),
                    "body_support": child.body_support,
                    "body_summary": child.body_summary,
                    "notices": list(child.notices),
                }
            )
        inspection.common["child_artifacts"] = child_artifacts
        return inspection
    return inspect_artifact_file(candidate)


def _model_labels(inspection: ArtifactInspection) -> dict[str, Any]:
    summary = inspection.body_summary or {}
    if summary.get("record_type") == "generation":
        return {
            "requested": summary.get("requested_model_label"),
            "reported": summary.get("reported_model_label"),
            "backend": summary.get("backend"),
        }
    if summary.get("record_type") in {
        "model_characterization",
        "model_characterization_campaign",
        "tool_decision_campaign",
    }:
        return {
            "requested": summary.get("model_label"),
            "reported": summary.get("model_label"),
            "backend": summary.get("backend"),
        }
    return {"requested": None, "reported": None, "backend": None}


def compare_artifacts(left: RunArtifact, right: RunArtifact) -> ArtifactComparison:
    """Compare defensible common facts without claiming execution equivalence."""

    left_inspection = inspect_artifact(left)
    right_inspection = inspect_artifact(right)
    left_labels = _model_labels(left_inspection)
    right_labels = _model_labels(right_inspection)
    labels_comparable = any(
        left_labels[key] is not None for key in ("requested", "reported")
    ) and any(right_labels[key] is not None for key in ("requested", "reported"))
    labels_equal = labels_comparable and left_labels == right_labels
    notices = [
        "model label equality is not model identity; digest, quantization, runtime, tokenizer, and template facts must be checked separately"
    ]
    if (
        left_inspection.body_support == "unsupported"
        or right_inspection.body_support == "unsupported"
    ):
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
    left_summary = left_inspection.body_summary or {}
    right_summary = right_inspection.body_summary or {}
    if (
        left_summary.get("record_type") == "model_characterization"
        and right_summary.get("record_type") == "model_characterization"
    ):
        left_statuses = left_summary.get("probe_statuses") or {}
        right_statuses = right_summary.get("probe_statuses") or {}
        comparable_ids = sorted(set(left_statuses) & set(right_statuses))
        common_facts["comparable_probe_ids"] = comparable_ids
        common_facts["changed_probe_statuses"] = {
            probe_id: {"left": left_statuses[probe_id], "right": right_statuses[probe_id]}
            for probe_id in comparable_ids
            if left_statuses[probe_id] != right_statuses[probe_id]
        }
        notices.append(
            "matching probe outcomes describe these runs only; they do not establish model or deployment equivalence"
        )
    if (
        left_summary.get("record_type") == "model_characterization_campaign"
        and right_summary.get("record_type") == "model_characterization_campaign"
    ):
        left_aggregates = left_summary.get("probe_aggregates") or {}
        right_aggregates = right_summary.get("probe_aggregates") or {}
        common_facts["comparable_probe_ids"] = sorted(set(left_aggregates) & set(right_aggregates))
        common_facts["campaign_aggregates_equal"] = left_aggregates == right_aggregates
        notices.append(
            "campaign aggregate differences are descriptive; this comparison does not test statistical significance"
        )
    if (
        left_summary.get("record_type") == "tool_decision_campaign"
        and right_summary.get("record_type") == "tool_decision_campaign"
    ):
        left_aggregates = left_summary.get("case_aggregates") or {}
        right_aggregates = right_summary.get("case_aggregates") or {}
        common_facts["comparable_case_ids"] = sorted(set(left_aggregates) & set(right_aggregates))
        common_facts["case_aggregates_equal"] = left_aggregates == right_aggregates
        common_facts["thinking_requested"] = {
            "left": left_summary.get("thinking_requested"),
            "right": right_summary.get("thinking_requested"),
            "equal": (
                left_summary.get("thinking_requested") == right_summary.get("thinking_requested")
            ),
        }
        notices.append(
            "tool-decision differences are descriptive observations from fixed synthetic cases, not explanations of hidden reasoning"
        )
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
