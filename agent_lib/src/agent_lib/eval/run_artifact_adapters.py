"""Adapters from legacy agent evaluation records to the shared artifact envelope."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from llm_harness_core import (
    Actor,
    ArtifactBundle,
    Attachment,
    AttachmentLocator,
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
    artifact_to_json_bytes,
    write_artifact_bundle,
)


ADAPTER_VERSION = "1"


@dataclass(frozen=True)
class ExperimentAdaptation:
    """An experiment artifact plus any published child artifacts it references."""

    experiment: RunArtifact
    children: tuple[RunArtifact, ...]


@dataclass(frozen=True)
class PreparedExperimentBundle:
    """A derived experiment artifact and the exact attachment bytes it declares."""

    artifact: RunArtifact
    attachment_bytes: Mapping[str, bytes]


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
        adapted_at=TimeValue(
            status="unknown", source="legacy adapter did not retain wall-clock adaptation time"
        ),
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


def _experiment_envelope(
    *,
    profile: str,
    digest: str,
    lifecycle: str,
    relationships: tuple[Relationship, ...],
    privacy_categories: tuple[str, ...],
    artifact_created_at: str | None = None,
) -> RecordEnvelope:
    time = TimeDeclaration(
        execution_started_at=TimeValue(status="unknown"),
        execution_finished_at=TimeValue(status="unknown"),
        artifact_created_at=(
            TimeValue(status="value", value=artifact_created_at, source="legacy campaign report")
            if artifact_created_at
            else None
        ),
        adapted_at=(
            None
            if artifact_created_at
            else TimeValue(
                status="unknown",
                source="legacy adapter did not retain wall-clock adaptation time",
            )
        ),
    )
    return RecordEnvelope(
        kind="experiment",
        envelope_schema_version=1,
        body_version=1,
        profile=profile,
        profile_version=1,
        record_id=_identity(profile, digest),
        lifecycle=lifecycle,
        relationships=(
            Relationship(
                relation_type="derived_from",
                target_kind=f"legacy_experiment.{profile}",
                target_id=f"sha256:{digest}",
            ),
            *relationships,
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
        time=time,
        privacy=_legacy_privacy(privacy_categories),
        omissions=(
            Omission(field_path="/time/execution_started_at", reason="absent_in_source_format"),
            Omission(field_path="/time/execution_finished_at", reason="absent_in_source_format"),
            Omission(field_path="/actors/original_producer", reason="absent_in_source_format"),
        ),
        capabilities=(),
        execution_environment={},
    )


def adapt_nav_v1(record: Mapping[str, Any]) -> RunArtifact:
    """Adapt one NAV schema-v1 mapping without mutating or replacing it."""

    source, digest = _canonical_source(record)
    if source.get("schema_version") != 1 or not isinstance(source.get("run"), dict):
        raise ValueError("expected a NAV schema-v1 run record")
    run = dict(source["run"])
    steps = list(run.get("steps") or [])
    profile_data = {
        key: value for key, value in source.items() if key not in {"schema_version", "run", "score"}
    }
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
            privacy_categories=(
                "prompt_or_task",
                "agent_trajectory",
                "tool_output",
                "filesystem_metadata",
            ),
            omissions=(
                Omission(field_path="/time/execution_started_at", reason="absent_in_source_format"),
                Omission(
                    field_path="/time/execution_finished_at", reason="absent_in_source_format"
                ),
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
        "task_id",
        "status",
        "stop_reason",
        "elapsed_seconds",
        "steps",
        "step_observations",
        "reasoning_trace",
        "worker",
        "mentor",
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
            privacy_categories=(
                "agent_reasoning",
                "tool_output",
                "evaluation_detail",
                "filesystem_metadata",
            ),
            omissions=(
                Omission(field_path="/time/execution_started_at", reason="absent_in_source_format"),
                Omission(
                    field_path="/time/execution_finished_at", reason="absent_in_source_format"
                ),
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


def adapt_asc_campaign(
    report: Mapping[str, Any],
    *,
    lifecycle: str,
) -> ExperimentAdaptation:
    """Adapt an ASC aggregate report without treating timeout rows as run artifacts.

    ``live_probe_results.json`` is rewritten throughout a probe and does not encode
    whether the requested matrix is complete. The caller must therefore declare
    whether the captured report is a checkpoint or a final result.
    """

    if lifecycle not in {"checkpoint", "final", "aborted"}:
        raise ValueError(f"invalid campaign lifecycle: {lifecycle}")
    source, digest = _canonical_source(report)
    records = source.get("records")
    summary = source.get("summary")
    if not isinstance(records, list) or not isinstance(summary, Mapping):
        raise ValueError("expected an ASC campaign report with records and summary")

    children: list[RunArtifact] = []
    items: list[dict[str, Any]] = []
    relationships: list[Relationship] = []
    item_ids: set[str] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise ValueError(f"ASC campaign record {index} is not an object")
        record = dict(raw)
        child: RunArtifact | None = None
        if record.get("status") == "completed":
            child = adapt_asc_record(record)
            children.append(child)
            relationships.append(
                Relationship(
                    relation_type="contains",
                    target_kind="agent_run",
                    target_id=child.envelope.record_id,
                )
            )
        item_id = f"{record.get('mode')}:{record.get('seed')}:{record.get('task_id')}"
        if item_id in item_ids:
            raise ValueError(f"duplicate ASC campaign item: {item_id}")
        item_ids.add(item_id)
        items.append(
            {
                "item_id": item_id,
                "child_record_id": child.envelope.record_id if child else None,
                "task_id": record.get("task_id"),
                "tier": record.get("tier"),
                "mode": record.get("mode"),
                "seed": record.get("seed"),
                "status": record.get("status"),
                "classification": record.get("classification"),
                "visible_pass": record.get("visible_pass"),
                "held_out_pass": record.get("held_out_pass"),
                "escalations": record.get("escalations"),
                "tamper_attempt_count": len(record.get("tamper_attempts") or []),
                "input_special_casing": record.get("input_special_casing"),
            }
        )

    body = {
        "campaign": {"name": "ASC live-model integrity probe"},
        "configuration": {},
        "items": items,
        "aggregate": deepcopy(dict(summary)),
        "decision": None,
        "profile_data": {"generated_at": source.get("generated_at")},
    }
    experiment = RunArtifact(
        envelope=_experiment_envelope(
            profile="agent_lib.asc_campaign",
            digest=digest,
            lifecycle=lifecycle,
            relationships=tuple(relationships),
            privacy_categories=(
                "experiment_configuration",
                "evaluation_detail",
                "child_run_identity",
            ),
            artifact_created_at=(
                str(source["generated_at"]) if source.get("generated_at") else None
            ),
        ),
        body=body,
    )
    return ExperimentAdaptation(experiment=experiment, children=tuple(children))


def adapt_nav_campaign(
    pairs: list[Mapping[str, Any]],
    *,
    summary: Mapping[str, Any] | None = None,
    decision: Mapping[str, Any] | None = None,
    arm_records: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> ExperimentAdaptation:
    """Adapt a NAV paired campaign checkpoint or completed result.

    A campaign is final only when both its separately written summary and
    decision are supplied. Published arm records are optional; when supplied,
    they become separately addressable child artifacts rather than embedded
    copies in the experiment body.
    """

    if (summary is None) != (decision is None):
        raise ValueError("NAV summary and decision must be supplied together")
    normalized_arm_records = dict(arm_records or {})
    arm_record_digests = {
        f"{task_id}:{mode}": _canonical_source(record)[1]
        for (task_id, mode), record in sorted(normalized_arm_records.items())
    }
    combined = {
        "pairs": deepcopy(list(pairs)),
        "summary": deepcopy(dict(summary)) if summary is not None else None,
        "decision": deepcopy(dict(decision)) if decision is not None else None,
        "arm_record_digests": arm_record_digests,
    }
    source, digest = _canonical_source(combined)
    children: list[RunArtifact] = []
    relationships: list[Relationship] = []
    child_ids: dict[tuple[str, str], str] = {}
    for key, raw_record in sorted(normalized_arm_records.items()):
        task_id, mode = key
        if mode not in {"no_ledger", "ledger"}:
            raise ValueError(f"invalid NAV campaign arm mode: {mode}")
        child = adapt_nav_v1(raw_record)
        children.append(child)
        child_ids[(str(task_id), mode)] = child.envelope.record_id
        relationships.append(
            Relationship(
                relation_type="contains",
                target_kind="agent_run",
                target_id=child.envelope.record_id,
            )
        )

    items: list[dict[str, Any]] = []
    task_ids: set[str] = set()
    for index, raw_pair in enumerate(source["pairs"]):
        if not isinstance(raw_pair, Mapping):
            raise ValueError(f"NAV campaign pair {index} is not an object")
        pair = dict(raw_pair)
        task_id = str(pair.get("task_id") or "")
        if (
            not task_id
            or not isinstance(pair.get("no_ledger"), Mapping)
            or not isinstance(pair.get("ledger"), Mapping)
        ):
            raise ValueError("NAV campaign pairs require task_id and both arm outcomes")
        if task_id in task_ids:
            raise ValueError(f"duplicate NAV campaign task: {task_id}")
        task_ids.add(task_id)
        items.append(
            {
                "item_id": task_id,
                "task_id": task_id,
                "tier": pair.get("tier"),
                "arms": {
                    mode: {
                        "child_record_id": child_ids.get((task_id, mode)),
                        "outcome": deepcopy(dict(pair[mode])),
                    }
                    for mode in ("no_ledger", "ledger")
                },
            }
        )

    extra_arm_keys = set(child_ids) - {
        (task_id, mode) for task_id in task_ids for mode in ("no_ledger", "ledger")
    }
    if extra_arm_keys:
        raise ValueError(
            f"NAV arm records do not belong to a campaign pair: {sorted(extra_arm_keys)}"
        )

    body = {
        "campaign": {"name": "NAV-VERIFIABLE-00", "design": "paired"},
        "configuration": {},
        "items": items,
        "aggregate": source["summary"],
        "decision": source["decision"],
        "profile_data": {},
    }
    experiment = RunArtifact(
        envelope=_experiment_envelope(
            profile="agent_lib.nav_verifiable_campaign",
            digest=digest,
            lifecycle="final" if summary is not None else "checkpoint",
            relationships=tuple(relationships),
            privacy_categories=(
                "experiment_configuration",
                "evaluation_detail",
                "child_run_identity",
            ),
        ),
        body=body,
    )
    return ExperimentAdaptation(experiment=experiment, children=tuple(children))


def prepare_experiment_bundle(
    adaptation: ExperimentAdaptation,
) -> PreparedExperimentBundle:
    """Prepare a new derived experiment snapshot with bundled child artifacts."""

    experiment = adaptation.experiment
    if experiment.envelope.kind != "experiment":
        raise ValueError("experiment bundle preparation requires an experiment artifact")
    children_by_id = {child.envelope.record_id: child for child in adaptation.children}
    if len(children_by_id) != len(adaptation.children):
        raise ValueError("experiment children must have unique record IDs")
    related_child_ids = {
        relationship.target_id
        for relationship in experiment.envelope.relationships
        if relationship.relation_type == "contains" and relationship.target_kind == "agent_run"
    }
    if set(children_by_id) != related_child_ids:
        raise ValueError("published experiment children must exactly match contains relationships")

    attachments: list[Attachment] = []
    attachment_bytes: dict[str, bytes] = {}
    reference_sensitivity = dict(experiment.envelope.privacy.reference_sensitivity)
    digest_inputs: list[dict[str, str]] = []
    for record_id, child in sorted(children_by_id.items()):
        data = artifact_to_json_bytes(child)
        digest = hashlib.sha256(data).hexdigest()
        attachment_id = f"child-{record_id}"
        relative_path = f"children/{record_id}.json"
        attachments.append(
            Attachment(
                attachment_id=attachment_id,
                logical_role="child_run_artifact",
                locator=AttachmentLocator(
                    type="bundled-file",
                    value=relative_path,
                    digest=digest,
                    digest_algorithm="sha256",
                ),
                declared_inclusion="bundled",
                requirement="optional",
            )
        )
        attachment_bytes[attachment_id] = data
        reference_sensitivity[attachment_id] = "unknown"
        digest_inputs.append({"record_id": record_id, "path": relative_path, "sha256": digest})

    _, bundle_digest = _canonical_source(
        {
            "source_record_id": experiment.envelope.record_id,
            "children": digest_inputs,
        }
    )
    bundle_record_id = _identity(
        f"{experiment.envelope.profile}.bundle",
        bundle_digest,
    )
    bundled_envelope = replace(
        experiment.envelope,
        record_id=bundle_record_id,
        relationships=(
            Relationship(
                relation_type="derived_from",
                target_kind="experiment",
                target_id=experiment.envelope.record_id,
            ),
            *experiment.envelope.relationships,
        ),
        attachments=tuple(attachments),
        actors=(
            *experiment.envelope.actors,
            Actor(
                actor_id="bundle_writer",
                role="recorder",
                name="agent_lib.experiment_bundle_writer",
                version=ADAPTER_VERSION,
            ),
        ),
        privacy=replace(
            experiment.envelope.privacy,
            reference_sensitivity=reference_sensitivity,
        ),
    )
    return PreparedExperimentBundle(
        artifact=RunArtifact(envelope=bundled_envelope, body=deepcopy(experiment.body)),
        attachment_bytes=attachment_bytes,
    )


def write_experiment_bundle(
    adaptation: ExperimentAdaptation,
    bundle_root: str | Path,
) -> ArtifactBundle:
    """Write a new portable experiment bundle to a previously absent directory."""

    prepared = prepare_experiment_bundle(adaptation)
    return write_artifact_bundle(
        prepared.artifact,
        bundle_root,
        prepared.attachment_bytes,
    )
