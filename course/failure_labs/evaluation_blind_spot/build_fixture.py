"""Build the privacy-safe offline fixture for the evaluation blind-spot lab."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from llm_harness_core import (
    Actor,
    Attachment,
    AttachmentLocator,
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


SOURCE_RELATIVE = Path("examples/asc_probe/runs/asc02_worker_only/live_probe_results.json")
SOURCE_SHA256 = "4de2f5dfa6a58a99c27d1fd22ceb7bad8997606045678b2dc684f5cf8e3d6ab5"
SELECTED = (
    (0, "honest_normalize_slug"),
    (0, "gt_bucket_label"),
    (0, "escalation_merge_intervals"),
)
CREATED_AT = "2026-06-20T17:00:39.887363+00:00"
POLICY_ID = "course-evaluation-summary-v1"


def _id(kind: str, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    return f"rr_{uuid5(NAMESPACE_URL, f'ai_tools:course:{kind}:{digest}').hex}"


def _privacy(*, references: dict[str, str] | None = None) -> PrivacyDeclaration:
    return PrivacyDeclaration(
        declared_content_categories=(
            "course_fixture",
            "evaluation_summary",
            "public_model_metadata",
        ),
        body_bytes_sensitivity="public",
        reference_sensitivity=references or {},
        transformations_applied=(
            {
                "policy_id": POLICY_ID,
                "policy_version": "1",
                "description": (
                    "allowlisted scalar outcome fields only; workspace paths, prompts, "
                    "reasoning, tool payloads, source code, and free-text details omitted"
                ),
            },
        ),
        validation=PrivacyValidation(
            status="validated",
            validator="course.failure_labs.evaluation_blind_spot.build_fixture",
            policy_id=POLICY_ID,
            policy_version="1",
            validated_at="2026-08-13T00:00:00+00:00",
            scope=(
                "allowlisted scalar body fields",
                "omission of source free text and filesystem paths",
            ),
        ),
    )


def _time() -> TimeDeclaration:
    return TimeDeclaration(
        execution_started_at=TimeValue(status="unknown"),
        execution_finished_at=TimeValue(status="unknown"),
        artifact_created_at=TimeValue(
            status="value",
            value=CREATED_AT,
            source="source campaign generated_at",
        ),
    )


def _select(source: dict[str, Any]) -> list[dict[str, Any]]:
    records = source.get("records")
    if not isinstance(records, list):
        raise ValueError("source campaign has no records list")
    by_key = {(record.get("seed"), record.get("task_id")): record for record in records}
    try:
        return [dict(by_key[key]) for key in SELECTED]
    except KeyError as exc:
        raise ValueError(f"source campaign is missing selected record: {exc.args[0]}") from exc


def _child(record: dict[str, Any]) -> RunArtifact:
    allowed = {
        key: record.get(key)
        for key in (
            "task_id",
            "tier",
            "mode",
            "seed",
            "status",
            "stop_reason",
            "steps",
            "classification",
            "visible_pass",
            "held_out_pass",
            "input_special_casing",
            "escalations",
        )
    }
    record_id = _id("agent_run", allowed)
    return RunArtifact(
        envelope=RecordEnvelope(
            kind="agent_run",
            envelope_schema_version=1,
            body_version=1,
            profile="agent_lib.asc",
            profile_version=1,
            record_id=record_id,
            lifecycle="final",
            relationships=(
                Relationship(
                    relation_type="derived_from",
                    target_kind="legacy_agent_run.agent_lib.asc",
                    target_id=f"course-source:{SOURCE_SHA256}:{record['seed']}:{record['task_id']}",
                ),
            ),
            attachments=(),
            actors=(
                Actor(
                    actor_id="recorder",
                    role="recorder",
                    name="course.evaluation_blind_spot_fixture",
                    version="1",
                ),
            ),
            time=_time(),
            privacy=_privacy(),
            execution_environment={
                "backend": "ollama",
                "model": "qwen3.6:27b",
                "quantization": "Q4",
            },
        ),
        body={
            "task": {"task_id": allowed["task_id"], "tier": allowed["tier"]},
            "status": allowed["status"],
            "stop_reason": allowed["stop_reason"],
            "elapsed_seconds": None,
            "step_count": allowed["steps"],
            "steps": [],
            "final_output": None,
            "model_roles": {
                "worker": {
                    "backend": "ollama",
                    "model": "qwen3.6:27b",
                    "quantization": "Q4",
                }
            },
            "evaluation": {
                "classification": allowed["classification"],
                "visible_pass": allowed["visible_pass"],
                "held_out_pass": allowed["held_out_pass"],
                "input_special_casing": allowed["input_special_casing"],
            },
            "profile_data": {
                "mode": allowed["mode"],
                "seed": allowed["seed"],
                "escalations": allowed["escalations"],
                "fixture_policy": POLICY_ID,
            },
        },
    )


def build(source_path: Path, output: Path) -> None:
    source_bytes = source_path.read_bytes()
    actual_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if actual_sha256 != SOURCE_SHA256:
        raise ValueError(
            f"source campaign digest changed: expected {SOURCE_SHA256}, got {actual_sha256}"
        )
    source = json.loads(source_bytes)
    children = tuple(_child(record) for record in _select(source))

    attachment_bytes: dict[str, bytes] = {}
    attachments: list[Attachment] = []
    relationships: list[Relationship] = []
    references: dict[str, str] = {}
    items: list[dict[str, Any]] = []
    for child in children:
        data = artifact_to_json_bytes(child)
        digest = hashlib.sha256(data).hexdigest()
        attachment_id = f"child-{child.envelope.record_id}"
        attachment_bytes[attachment_id] = data
        references[attachment_id] = "public"
        attachments.append(
            Attachment(
                attachment_id=attachment_id,
                logical_role="child_run_artifact",
                locator=AttachmentLocator(
                    type="bundled-file",
                    value=f"children/{child.envelope.record_id}.json",
                    digest=digest,
                    digest_algorithm="sha256",
                ),
                declared_inclusion="bundled",
                requirement="required",
            )
        )
        relationships.append(
            Relationship(
                relation_type="contains",
                target_kind="agent_run",
                target_id=child.envelope.record_id,
            )
        )
        evaluation = dict(child.body["evaluation"])
        items.append(
            {
                "item_id": child.body["task"]["task_id"],
                "child_record_id": child.envelope.record_id,
                "status": child.body["status"],
                **evaluation,
            }
        )

    experiment_body = {
        "campaign": {
            "name": "Evaluation blind spot: green visible checks can hide failure",
            "design": "three representative outcomes from one local-model campaign",
        },
        "configuration": {
            "backend": "ollama",
            "model": "qwen3.6:27b",
            "mode": "worker-only",
            "seed": 0,
        },
        "items": items,
        "aggregate": {
            "source_runs": source["summary"]["runs"],
            "source_timeouts": source["summary"]["timeouts"],
            "source_headline_worker_only_gaming_rate": source["summary"][
                "headline_worker_only_gaming_rate"
            ],
            "fixture_items": len(items),
        },
        "decision": None,
        "profile_data": {
            "source_path": SOURCE_RELATIVE.as_posix(),
            "source_sha256": SOURCE_SHA256,
            "selection": "seed 0; one both-pass, one visible-fail/held-out-pass, one visible-pass/held-out-fail",
        },
    }
    experiment_id = _id("experiment", experiment_body)
    experiment = RunArtifact(
        envelope=RecordEnvelope(
            kind="experiment",
            envelope_schema_version=1,
            body_version=1,
            profile="agent_lib.asc_campaign",
            profile_version=1,
            record_id=experiment_id,
            lifecycle="final",
            relationships=tuple(relationships),
            attachments=tuple(attachments),
            actors=(
                Actor(
                    actor_id="recorder",
                    role="recorder",
                    name="course.evaluation_blind_spot_fixture",
                    version="1",
                ),
            ),
            time=_time(),
            privacy=_privacy(references=references),
            execution_environment={"recorded_fixture": True},
        ),
        body=experiment_body,
    )
    write_artifact_bundle(experiment, output, attachment_bytes)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repo_root / SOURCE_RELATIVE)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "fixture")
    args = parser.parse_args()
    build(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
