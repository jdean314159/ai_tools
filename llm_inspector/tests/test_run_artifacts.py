from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from llm_harness_core import (
    Actor,
    Omission,
    PrivacyDeclaration,
    PrivacyValidation,
    RecordEnvelope,
    RunArtifact,
    TimeDeclaration,
    TimeValue,
    dump_artifact,
)
from llm_inspector.artifacts import (
    compare_artifacts,
    inspect_artifact,
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


def test_generation_and_agent_dispatch_to_different_summaries() -> None:
    generation = inspect_artifact(_generation())
    agent = inspect_artifact(_agent())

    assert generation.body_support == "supported"
    assert generation.body_summary["record_type"] == "generation"
    assert generation.body_summary["finish_reason"] == "stop"
    assert agent.body_support == "supported"
    assert agent.body_summary["record_type"] == "agent_run"
    assert agent.body_summary["step_count"] == 2


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
    }


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
