from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

from llm_harness_core import (
    Actor,
    Attachment,
    AttachmentLocator,
    Omission,
    PrivacyDeclaration,
    PrivacyValidation,
    RecordEnvelope,
    RunArtifact,
    TimeDeclaration,
    TimeValue,
    dump_artifact,
    write_artifact_bundle,
)
from llm_inspector.artifacts import (
    compare_artifacts,
    inspect_artifact,
    inspect_artifact_path,
    render_artifact_comparison,
    render_artifact_inspection,
)
from llm_inspector.cli import main


def _envelope(*, kind="generation", profile=None, profile_version=None, body_version=1):
    return RecordEnvelope(
        kind=kind,
        envelope_schema_version=1,
        body_version=body_version,
        profile=profile,
        profile_version=profile_version,
        record_id=f"rr_{profile or kind}",
        lifecycle="final",
        relationships=(),
        attachments=(),
        actors=(Actor(actor_id="recorder", role="recorder", name="fixture"),),
        time=TimeDeclaration(
            execution_started_at=TimeValue(status="unknown"),
            execution_finished_at=TimeValue(status="unknown"),
            artifact_created_at=TimeValue(status="value", value="2026-08-13T00:00:00Z"),
        ),
        privacy=PrivacyDeclaration(
            declared_content_categories=("synthetic",),
            body_bytes_sensitivity="public",
            validation=PrivacyValidation(status="validated", scope=("fixture",)),
        ),
        omissions=(Omission(field_path="/body/example", reason="not_reported_by_backend"),),
    )


def _generation(*, reported="fixture-model") -> RunArtifact:
    return RunArtifact(
        envelope=_envelope(),
        body={
            "outcome": "completed",
            "request": {"json_schema": None},
            "response": {
                "finish_reason": "stop",
                "message": {"content": "fixture", "tool_calls": []},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
            "model_identity": {
                "requested_label": "fixture-model",
                "reported_label": reported,
                "backend": "mock",
            },
        },
    )


def _agent(profile="agent_lib.nav") -> RunArtifact:
    return RunArtifact(
        envelope=_envelope(kind="agent_run", profile=profile, profile_version=1),
        body={
            "task": {"task_id": "fixture-task"},
            "status": "completed",
            "stop_reason": "final",
            "elapsed_seconds": 1.0,
            "step_count": 2,
            "steps": [{}, {}],
            "final_output": "fixture",
            "model_roles": {"planner": {}},
            "evaluation": {"passed": True},
        },
    )


def _experiment(profile="agent_lib.asc_campaign") -> RunArtifact:
    envelope = _envelope(kind="experiment", profile=profile, profile_version=1)
    return RunArtifact(
        envelope=replace(envelope, lifecycle="checkpoint"),
        body={
            "campaign": {"name": "fixture campaign"},
            "configuration": {},
            "items": [{"item_id": "one"}, {"item_id": "two"}],
            "aggregate": {"runs": 2},
            "decision": None,
            "profile_data": {},
        },
    )


def _characterization() -> RunArtifact:
    return RunArtifact(
        envelope=_envelope(
            kind="experiment",
            profile="llm_engines.model_characterization",
            profile_version=2,
        ),
        body={
            "backend": "openai",
            "model_label": "fixture-model",
            "thinking_requested": None,
            "probes": [
                {"probe_id": "chat_exact_text", "status": "passed"},
                {"probe_id": "tool_call", "status": "not_declared"},
            ],
            "interpretation_limit": "observable behavior only",
        },
    )


def _characterization_campaign() -> RunArtifact:
    return RunArtifact(
        envelope=_envelope(
            kind="experiment",
            profile="llm_engines.model_characterization_campaign",
            profile_version=2,
        ),
        body={
            "backend": "openai",
            "model_label": "fixture-model",
            "thinking_requested": None,
            "repetitions": 3,
            "probe_aggregates": {
                "chat_exact_text": {
                    "runs": 3,
                    "status_counts": {"passed": 3},
                    "status_stable": True,
                    "pass_rate": 1.0,
                }
            },
            "interpretation_limit": "descriptive observations only",
        },
    )


def _tool_decision_campaign(*, thinking: bool) -> RunArtifact:
    return RunArtifact(
        envelope=_envelope(
            kind="experiment",
            profile="llm_engines.tool_decision_campaign",
            profile_version=2,
        ),
        body={
            "backend": "openai",
            "model_label": "fixture-model",
            "repetitions": 2,
            "cases_per_run": 1,
            "thinking_requested": thinking,
            "case_aggregates": {
                "required_single_tool": {"runs": 2, "passed": 2, "pass_rate": 1.0}
            },
            "interpretation_limit": "observable decisions only",
        },
    )


def test_generation_and_agent_dispatch_to_different_summaries() -> None:
    generation = inspect_artifact(_generation())
    agent = inspect_artifact(_agent())

    assert generation.body_support == "supported"
    assert generation.body_summary["record_type"] == "generation"
    assert generation.body_summary["finish_reason"] == "stop"
    assert agent.body_support == "supported"
    assert agent.body_summary["record_type"] == "agent_run"
    assert agent.body_summary["step_count"] == 2
    assert agent.body_summary["evaluation_signals"] == {}


def test_experiment_dispatch_preserves_campaign_semantics() -> None:
    inspection = inspect_artifact(_experiment())

    assert inspection.body_support == "supported"
    assert inspection.body_summary == {
        "record_type": "experiment",
        "profile": "agent_lib.asc_campaign",
        "campaign_name": "fixture campaign",
        "lifecycle": "checkpoint",
        "item_count": 2,
        "child_record_count": 0,
        "has_aggregate": True,
        "has_decision": False,
        "aggregate_signals": {"runs": 2},
        "decision_signals": {},
    }


def test_characterization_dispatch_reports_probe_outcomes() -> None:
    inspection = inspect_artifact(_characterization())

    assert inspection.body_support == "supported"
    assert inspection.body_summary == {
        "record_type": "model_characterization",
        "profile": "llm_engines.model_characterization",
        "backend": "openai",
        "model_label": "fixture-model",
        "thinking_requested": None,
        "probe_count": 2,
        "status_counts": {"passed": 1, "not_declared": 1},
        "probe_statuses": {
            "chat_exact_text": "passed",
            "tool_call": "not_declared",
        },
        "interpretation_limit": "observable behavior only",
    }


def test_characterization_comparison_reports_changed_probe_status() -> None:
    left = _characterization()
    right_body = dict(left.body)
    right_body["probes"] = [
        {"probe_id": "chat_exact_text", "status": "failed"},
        {"probe_id": "tool_call", "status": "not_declared"},
    ]
    comparison = compare_artifacts(left, replace(left, body=right_body))

    assert comparison.common_facts["changed_probe_statuses"] == {
        "chat_exact_text": {"left": "passed", "right": "failed"}
    }
    assert comparison.common_facts["model_identity_equal"] == "not_determined"
    assert any("these runs only" in notice for notice in comparison.notices)


def test_characterization_campaign_summary_and_comparison_are_descriptive() -> None:
    artifact = _characterization_campaign()
    inspection = inspect_artifact(artifact)
    comparison = compare_artifacts(artifact, artifact)

    assert inspection.body_support == "supported"
    assert inspection.body_summary["record_type"] == "model_characterization_campaign"
    assert inspection.body_summary["repetitions"] == 3
    assert comparison.common_facts["campaign_aggregates_equal"] is True
    assert any("statistical significance" in notice for notice in comparison.notices)


def test_tool_decision_comparison_surfaces_thinking_setting() -> None:
    comparison = compare_artifacts(
        _tool_decision_campaign(thinking=False),
        _tool_decision_campaign(thinking=True),
    )

    assert comparison.left.body_support == "supported"
    assert comparison.common_facts["thinking_requested"] == {
        "left": False,
        "right": True,
        "equal": False,
    }
    assert any("hidden reasoning" in notice for notice in comparison.notices)


def test_unsupported_profile_keeps_envelope_and_refuses_body_interpretation() -> None:
    artifact = _agent("unknown.profile")

    inspection = inspect_artifact(artifact)

    assert inspection.common["record_id"] == "rr_unknown.profile"
    assert inspection.body_support == "unsupported"
    assert inspection.body_summary is None
    assert any("unsupported" in notice for notice in inspection.notices)


def test_unvalidated_privacy_and_omissions_are_visible() -> None:
    artifact = _generation()
    privacy = replace(artifact.envelope.privacy, validation=PrivacyValidation(status="not_validated"))
    artifact = replace(artifact, envelope=replace(artifact.envelope, privacy=privacy))

    inspection = inspect_artifact(artifact)

    assert inspection.common["privacy"]["validation_status"] == "not_validated"
    assert inspection.common["omissions"] == [
        {"field_path": "/body/example", "reason": "not_reported_by_backend"}
    ]
    assert "privacy declaration is not validated" in inspection.notices


def test_comparison_never_promotes_matching_labels_to_model_identity() -> None:
    comparison = compare_artifacts(_generation(), _generation())

    assert comparison.common_facts["model_labels_equal"] is True
    assert comparison.common_facts["model_identity_equal"] == "not_determined"
    assert any("not model identity" in notice for notice in comparison.notices)


def test_cross_kind_comparison_is_common_facts_only() -> None:
    comparison = compare_artifacts(_generation(), _agent())

    assert comparison.common_facts["same_kind"] is False
    assert comparison.common_facts["same_body_contract"] is False
    assert comparison.common_facts["model_labels_comparable"] is False


def test_text_renderers_surface_support_and_identity_warning() -> None:
    assert "body support: supported" in render_artifact_inspection(inspect_artifact(_generation()))
    assert "model label equality is not model identity" in render_artifact_comparison(
        compare_artifacts(_generation(), _generation())
    )


def test_artifact_cli_show_and_compare(tmp_path: Path, capsys) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    dump_artifact(_generation(), left)
    dump_artifact(_agent(), right)

    assert main(["artifact", "show", str(left), "--format", "json"]) == 0
    shown = capsys.readouterr().out
    assert '"record_type": "generation"' in shown

    assert main(["artifact", "compare", str(left), str(right)]) == 0
    compared = capsys.readouterr().out
    assert "same_kind: false" in compared
    assert "model_identity_equal: \"not_determined\"" in compared


def _bundled_experiment(data: bytes) -> RunArtifact:
    attachment = Attachment(
        attachment_id="child",
        logical_role="child_run_artifact",
        locator=AttachmentLocator(
            type="bundled-file",
            value="children/child.json",
            digest=hashlib.sha256(data).hexdigest(),
            digest_algorithm="sha256",
        ),
        declared_inclusion="bundled",
        requirement="optional",
    )
    artifact = _experiment()
    return replace(
        artifact,
        envelope=replace(
            artifact.envelope,
            attachments=(attachment,),
            privacy=replace(
                artifact.envelope.privacy,
                reference_sensitivity={"child": "public"},
            ),
        ),
    )


def test_bundle_inspection_surfaces_resolution_without_printing_local_path(tmp_path: Path) -> None:
    data = b"child artifact bytes"
    root = tmp_path / "bundle"
    write_artifact_bundle(_bundled_experiment(data), root, {"child": data})

    inspection = inspect_artifact_path(root)

    assert inspection.common["attachment_resolutions"] == [
        {
            "attachment_id": "child",
            "status": "resolved",
            "declared_inclusion": "bundled",
            "requirement": "optional",
            "detail": None,
        }
    ]
    assert str(tmp_path) not in render_artifact_inspection(inspection)


def test_bundle_cli_reports_digest_mismatch(tmp_path: Path, capsys) -> None:
    data = b"child artifact bytes"
    root = tmp_path / "bundle"
    write_artifact_bundle(_bundled_experiment(data), root, {"child": data})
    (root / "children/child.json").write_bytes(b"tampered")

    assert main(["artifact", "show", str(root), "--format", "json"]) == 0
    shown = capsys.readouterr().out
    assert '"status": "digest_mismatch"' in shown
    assert "has a digest mismatch" in shown
