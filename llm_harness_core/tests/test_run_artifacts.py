from __future__ import annotations

from dataclasses import replace

import pytest

from llm_harness_core import (
    Actor,
    ArtifactValidationError,
    Attachment,
    AttachmentLocator,
    PrivacyDeclaration,
    PrivacyValidation,
    RecordEnvelope,
    RunArtifact,
    SupportedBodyContract,
    TimeDeclaration,
    TimeValue,
    UnsupportedEnvelopeVersionError,
    artifact_from_dict,
    artifact_to_dict,
    body_support_status,
    dump_artifact,
    load_artifact,
    summarize_artifact,
)
from llm_harness_core.run_artifacts_cli import main


def _artifact() -> RunArtifact:
    return RunArtifact(
        envelope=RecordEnvelope(
            kind="agent_run",
            envelope_schema_version=1,
            body_version=1,
            record_id="rr_test",
            lifecycle="final",
            profile="test.profile",
            profile_version=1,
            relationships=(),
            attachments=(
                Attachment(
                    attachment_id="environment",
                    logical_role="environment_manifest",
                    locator=AttachmentLocator(
                        type="bundled-file",
                        value="attachments/environment.json",
                        digest="abc",
                        digest_algorithm="sha256",
                    ),
                    declared_inclusion="bundled",
                    requirement="optional",
                ),
            ),
            actors=(Actor(actor_id="recorder", role="recorder", name="test"),),
            time=TimeDeclaration(
                execution_started_at=TimeValue(status="unknown"),
                execution_finished_at=TimeValue(status="unknown"),
                artifact_created_at=TimeValue(status="value", value="2026-08-13T00:00:00Z"),
            ),
            privacy=PrivacyDeclaration(
                declared_content_categories=("synthetic",),
                body_bytes_sensitivity="public",
                validation=PrivacyValidation(status="validated", scope=("body",)),
            ),
        ),
        body={"status": "completed", "steps": []},
    )


def test_artifact_round_trip_preserves_body_and_envelope() -> None:
    original = _artifact()
    payload = artifact_to_dict(original)
    payload["envelope"]["future_envelope_field"] = "ignored"
    payload["body"]["future_body_field"] = {"preserved": True}

    parsed = artifact_from_dict(payload)

    assert parsed.envelope == original.envelope
    assert parsed.body["future_body_field"] == {"preserved": True}
    assert summarize_artifact(parsed)["profile"] == "test.profile"


def test_unknown_envelope_version_fails() -> None:
    payload = artifact_to_dict(_artifact())
    payload["envelope"]["envelope_schema_version"] = 2

    with pytest.raises(UnsupportedEnvelopeVersionError):
        artifact_from_dict(payload)


def test_unknown_body_version_keeps_envelope_readable_but_reports_unsupported() -> None:
    artifact = RunArtifact(envelope=replace(_artifact().envelope, body_version=99), body={"future": True})
    parsed = artifact_from_dict(artifact_to_dict(artifact))

    assert parsed.envelope.record_id == "rr_test"
    assert body_support_status(
        parsed,
        (SupportedBodyContract(kind="agent_run", body_version=1, profile="test.profile", profile_version=1),),
    ) == "unsupported"


def test_envelope_requires_recorder_or_adapter() -> None:
    with pytest.raises(ArtifactValidationError, match="recorder or adapter"):
        replace(_artifact().envelope, actors=())


def test_bundle_locator_rejects_absolute_or_parent_path() -> None:
    with pytest.raises(ArtifactValidationError, match="bundle-relative"):
        AttachmentLocator(
            type="bundled-file",
            value="../secret.json",
            digest="abc",
            digest_algorithm="sha256",
        )


def test_file_round_trip_preserves_scoped_privacy_declaration(tmp_path) -> None:
    original = _artifact()
    path = tmp_path / "record.json"

    dump_artifact(original, path)
    loaded = load_artifact(path)

    assert loaded == original
    assert loaded.envelope.privacy.validation.scope == ("body",)


def test_cli_validates_and_summarizes(tmp_path, capsys) -> None:
    path = tmp_path / "record.json"
    dump_artifact(_artifact(), path)

    assert main([str(path)]) == 0
    output = capsys.readouterr().out
    assert '"record_id": "rr_test"' in output
    assert '"body_interpretation": "not_evaluated"' in output
