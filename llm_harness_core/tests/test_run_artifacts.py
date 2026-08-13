from __future__ import annotations

from dataclasses import replace
import hashlib

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
    artifact_to_json_bytes,
    body_support_status,
    dump_artifact,
    load_artifact,
    load_artifact_bundle,
    resolve_artifact_attachments,
    summarize_artifact,
    write_artifact_bundle,
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
                reference_sensitivity={"environment": "public"},
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


def test_bundle_writer_requires_matching_reference_sensitivity(tmp_path) -> None:
    artifact = replace(
        _artifact(),
        envelope=replace(
            _artifact().envelope,
            privacy=replace(_artifact().envelope.privacy, reference_sensitivity={}),
        ),
    )
    with pytest.raises(ArtifactValidationError, match="reference-sensitivity"):
        write_artifact_bundle(
            artifact,
            tmp_path / "bundle",
            {"environment": b"fixture"},
        )


def test_legacy_envelope_without_attachment_sensitivity_remains_readable() -> None:
    payload = artifact_to_dict(_artifact())
    payload["envelope"]["privacy"]["reference_sensitivity"] = {}

    parsed = artifact_from_dict(payload)

    assert parsed.envelope.attachments[0].attachment_id == "environment"


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


def _artifact_with_attachment(data: bytes, *, requirement="required") -> RunArtifact:
    attachment = replace(
        _artifact().envelope.attachments[0],
        requirement=requirement,
        locator=replace(
            _artifact().envelope.attachments[0].locator,
            digest=hashlib.sha256(data).hexdigest(),
        ),
    )
    return replace(
        _artifact(),
        envelope=replace(_artifact().envelope, attachments=(attachment,)),
    )


def test_bundle_write_load_and_exact_byte_digest(tmp_path) -> None:
    data = b'{"fixture": true}\n'
    artifact = _artifact_with_attachment(data)
    root = tmp_path / "bundle"

    written = write_artifact_bundle(artifact, root, {"environment": data})
    loaded = load_artifact_bundle(root)

    assert written == loaded
    assert loaded.artifact == artifact
    assert loaded.resolutions[0].status == "resolved"
    assert (root / "record.json").read_bytes() == artifact_to_json_bytes(artifact)
    assert (root / "attachments/environment.json").read_bytes() == data


def test_bundle_writer_rejects_digest_mismatch_without_publishing_target(tmp_path) -> None:
    artifact = _artifact_with_attachment(b"expected")
    root = tmp_path / "bundle"

    with pytest.raises(ArtifactValidationError, match="digest mismatch"):
        write_artifact_bundle(artifact, root, {"environment": b"different"})

    assert not root.exists()


def test_resolution_distinguishes_missing_mismatch_and_detached(tmp_path) -> None:
    data = b"expected"
    artifact = _artifact_with_attachment(data)
    missing = resolve_artifact_attachments(artifact, tmp_path)
    assert missing[0].status == "unresolved"
    assert missing[0].requirement == "required"

    path = tmp_path / "attachments" / "environment.json"
    path.parent.mkdir()
    path.write_bytes(b"different")
    mismatch = resolve_artifact_attachments(artifact, tmp_path)
    assert mismatch[0].status == "digest_mismatch"

    detached_attachment = replace(
        artifact.envelope.attachments[0],
        declared_inclusion="detached",
        requirement="optional",
        locator=AttachmentLocator(
            type="digest-only",
            digest=hashlib.sha256(data).hexdigest(),
            digest_algorithm="sha256",
        ),
    )
    detached = replace(
        artifact,
        envelope=replace(artifact.envelope, attachments=(detached_attachment,)),
    )
    result = resolve_artifact_attachments(detached, tmp_path)
    assert result[0].status == "unresolved"
    assert result[0].declared_inclusion == "detached"
    assert "intentionally detached" in result[0].detail


def test_resolution_rejects_symlink_escape(tmp_path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"expected")
    bundle = tmp_path / "bundle"
    attachments = bundle / "attachments"
    attachments.mkdir(parents=True)
    (attachments / "environment.json").symlink_to(outside)
    artifact = _artifact_with_attachment(b"expected")

    result = resolve_artifact_attachments(artifact, bundle)

    assert result[0].status == "unresolved"
    assert "symbolic link" in result[0].detail


def test_bundle_writer_never_overwrites_existing_target(tmp_path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()

    with pytest.raises(FileExistsError):
        write_artifact_bundle(_artifact_with_attachment(b"fixture"), root, {"environment": b"fixture"})


def test_bundle_loader_rejects_root_artifact_escape(tmp_path) -> None:
    with pytest.raises(ArtifactValidationError, match="artifact filename"):
        load_artifact_bundle(tmp_path, artifact_filename="../record.json")
