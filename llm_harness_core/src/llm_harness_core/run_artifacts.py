"""Dependency-free contracts for durable LLM run artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Literal, Mapping


ENVELOPE_SCHEMA_VERSION = 1
RecordKind = Literal["agent_run", "generation", "experiment"]
Lifecycle = Literal["checkpoint", "final", "aborted"]


class ArtifactValidationError(ValueError):
    """Raised when a run artifact violates the supported envelope contract."""


class UnsupportedEnvelopeVersionError(ArtifactValidationError):
    """Raised when common envelope metadata cannot be interpreted safely."""


@dataclass(frozen=True)
class Relationship:
    relation_type: str
    target_kind: str
    target_id: str


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: Literal["original_producer", "recorder", "adapter", "user"]
    name: str
    version: str | None = None

    def __post_init__(self) -> None:
        if self.role not in {"original_producer", "recorder", "adapter", "user"}:
            raise ArtifactValidationError(f"invalid actor role: {self.role}")
        if not self.actor_id or not self.name:
            raise ArtifactValidationError("actor_id and actor name must not be empty")


@dataclass(frozen=True)
class TimeValue:
    status: Literal["value", "unknown", "not_applicable"]
    value: str | None = None
    source: str | None = None
    precision: str | None = None

    def __post_init__(self) -> None:
        if self.status == "value" and not self.value:
            raise ArtifactValidationError("time status 'value' requires a value")
        if self.status != "value" and self.value is not None:
            raise ArtifactValidationError("unknown/not_applicable time cannot carry a value")


@dataclass(frozen=True)
class TimeDeclaration:
    execution_started_at: TimeValue
    execution_finished_at: TimeValue
    artifact_created_at: TimeValue | None = None
    adapted_at: TimeValue | None = None

    def __post_init__(self) -> None:
        if self.artifact_created_at is None and self.adapted_at is None:
            raise ArtifactValidationError(
                "artifact_created_at or adapted_at must be declared"
            )


@dataclass(frozen=True)
class PrivacyValidation:
    status: Literal["not_validated", "partially_validated", "validated"]
    scope: tuple[str, ...] = ()
    validator: str | None = None
    policy_id: str | None = None
    policy_version: str | None = None
    validated_at: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"not_validated", "partially_validated", "validated"}:
            raise ArtifactValidationError(f"invalid privacy validation status: {self.status}")


@dataclass(frozen=True)
class PrivacyDeclaration:
    declared_content_categories: tuple[str, ...]
    body_bytes_sensitivity: str
    reference_sensitivity: Mapping[str, str] = field(default_factory=dict)
    transformations_applied: tuple[Mapping[str, Any], ...] = ()
    validation: PrivacyValidation = field(
        default_factory=lambda: PrivacyValidation(status="not_validated")
    )

    def __post_init__(self) -> None:
        if not self.body_bytes_sensitivity:
            raise ArtifactValidationError("body_bytes_sensitivity must be declared")


@dataclass(frozen=True)
class Omission:
    field_path: str
    reason: Literal[
        "not_reported_by_backend",
        "redacted",
        "not_applicable",
        "absent_in_source_format",
        "capture_failed",
        "intentionally_not_recorded",
        "unsupported_by_recorder",
    ]

    def __post_init__(self) -> None:
        if not self.field_path.startswith("/"):
            raise ArtifactValidationError("omission field_path must be an absolute artifact path")


@dataclass(frozen=True)
class AttachmentLocator:
    type: Literal["bundled-file", "content-uri", "resolver-key", "digest-only"]
    digest: str
    digest_algorithm: str
    value: str | None = None

    def __post_init__(self) -> None:
        if self.type not in {"bundled-file", "content-uri", "resolver-key", "digest-only"}:
            raise ArtifactValidationError(f"invalid attachment locator type: {self.type}")
        if not self.digest or not self.digest_algorithm:
            raise ArtifactValidationError("attachment digest and algorithm are required")
        if self.type != "digest-only" and not self.value:
            raise ArtifactValidationError(f"{self.type} locator requires a value")
        if self.type == "bundled-file" and self.value is not None:
            candidate = Path(self.value)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ArtifactValidationError(
                    "bundled-file locator must be a confined bundle-relative path"
                )


@dataclass(frozen=True)
class Attachment:
    attachment_id: str
    logical_role: str
    locator: AttachmentLocator
    declared_inclusion: Literal["bundled", "detached"]
    requirement: Literal["required", "optional"]

    def __post_init__(self) -> None:
        if self.declared_inclusion not in {"bundled", "detached"}:
            raise ArtifactValidationError(f"invalid attachment inclusion: {self.declared_inclusion}")
        if self.requirement not in {"required", "optional"}:
            raise ArtifactValidationError(f"invalid attachment requirement: {self.requirement}")


@dataclass(frozen=True)
class CapabilityRequirement:
    type: Literal[
        "attachment", "body_path", "external_service", "implementation", "configuration"
    ]
    ref: str


@dataclass(frozen=True)
class DeterminismClaim:
    claim: Literal["not_claimed", "deterministic", "best_effort"]
    evidence_basis: Literal["declared", "statically_validated", "exercised"]
    conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.claim not in {"not_claimed", "deterministic", "best_effort"}:
            raise ArtifactValidationError(f"invalid determinism claim: {self.claim}")
        if self.evidence_basis not in {"declared", "statically_validated", "exercised"}:
            raise ArtifactValidationError(f"invalid determinism evidence basis: {self.evidence_basis}")


@dataclass(frozen=True)
class CapabilityClaim:
    operation: str
    requirements: tuple[CapabilityRequirement, ...]
    execution_mode: Literal["recorded", "local_compute", "live_external"]
    effect_class: Literal["none", "read_only", "state_changing", "unknown"]
    determinism: DeterminismClaim
    implementation_version: str

    def __post_init__(self) -> None:
        if self.execution_mode not in {"recorded", "local_compute", "live_external"}:
            raise ArtifactValidationError(f"invalid execution mode: {self.execution_mode}")
        if self.effect_class not in {"none", "read_only", "state_changing", "unknown"}:
            raise ArtifactValidationError(f"invalid effect class: {self.effect_class}")


@dataclass(frozen=True)
class RecordEnvelope:
    kind: RecordKind
    envelope_schema_version: int
    body_version: int
    record_id: str
    lifecycle: Lifecycle
    profile: str | None
    profile_version: int | None
    relationships: tuple[Relationship, ...]
    attachments: tuple[Attachment, ...]
    actors: tuple[Actor, ...]
    time: TimeDeclaration
    privacy: PrivacyDeclaration
    omissions: tuple[Omission, ...] = ()
    capabilities: tuple[CapabilityClaim, ...] = ()
    execution_environment: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.envelope_schema_version != ENVELOPE_SCHEMA_VERSION:
            raise UnsupportedEnvelopeVersionError(
                f"unsupported envelope schema version: {self.envelope_schema_version}"
            )
        if not self.record_id:
            raise ArtifactValidationError("record_id must not be empty")
        if self.kind not in {"agent_run", "generation", "experiment"}:
            raise ArtifactValidationError(f"unsupported record kind: {self.kind}")
        if self.lifecycle not in {"checkpoint", "final", "aborted"}:
            raise ArtifactValidationError(f"invalid lifecycle: {self.lifecycle}")
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ArtifactValidationError("actor IDs must be unique")
        if not any(actor.role in {"recorder", "adapter"} for actor in self.actors):
            raise ArtifactValidationError("at least one recorder or adapter is required")
        if self.profile_version is not None and self.profile is None:
            raise ArtifactValidationError("profile_version requires profile")


@dataclass(frozen=True)
class RunArtifact:
    envelope: RecordEnvelope
    body: Mapping[str, Any]


@dataclass(frozen=True)
class AttachmentResolution:
    """Reader-computed state for one attachment in a particular bundle copy."""

    attachment_id: str
    status: Literal["resolved", "unresolved", "digest_mismatch"]
    declared_inclusion: Literal["bundled", "detached"]
    requirement: Literal["required", "optional"]
    resolved_path: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ArtifactBundle:
    """A loaded root artifact and attachment observations for one bundle path."""

    artifact: RunArtifact
    resolutions: tuple[AttachmentResolution, ...]
    root: Path


@dataclass(frozen=True)
class SupportedBodyContract:
    kind: str
    body_version: int
    profile: str | None = None
    profile_version: int | None = None


def body_support_status(
    artifact: RunArtifact,
    supported: tuple[SupportedBodyContract, ...],
) -> Literal["supported", "unsupported"]:
    """Report body support without weakening envelope validation."""

    envelope = artifact.envelope
    for contract in supported:
        if (
            contract.kind == envelope.kind
            and contract.body_version == envelope.body_version
            and contract.profile == envelope.profile
            and contract.profile_version == envelope.profile_version
        ):
            return "supported"
    return "unsupported"


def artifact_to_dict(artifact: RunArtifact) -> dict[str, Any]:
    """Return a JSON-compatible representation of an artifact."""

    return asdict(artifact)


def artifact_to_json_bytes(artifact: RunArtifact) -> bytes:
    """Serialize the exact UTF-8 byte representation used by bundle digests."""

    return (
        json.dumps(artifact_to_dict(artifact), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _construct(cls: type[Any], payload: Mapping[str, Any], **overrides: Any) -> Any:
    accepted = {item.name for item in fields(cls)}
    values = {key: value for key, value in payload.items() if key in accepted}
    values.update(overrides)
    try:
        return cls(**values)
    except TypeError as exc:
        raise ArtifactValidationError(f"invalid {cls.__name__}: {exc}") from exc


def artifact_from_dict(payload: Mapping[str, Any]) -> RunArtifact:
    """Parse and validate a version-1 run artifact mapping."""

    if not isinstance(payload, Mapping):
        raise ArtifactValidationError("artifact must be an object")
    raw_envelope = payload.get("envelope")
    body = payload.get("body")
    if not isinstance(raw_envelope, Mapping) or not isinstance(body, Mapping):
        raise ArtifactValidationError("artifact requires object envelope and body fields")

    try:
        relationships = tuple(
            _construct(Relationship, item) for item in raw_envelope.get("relationships", ())
        )
        attachments = tuple(
            _construct(
                Attachment,
                item,
                locator=_construct(AttachmentLocator, item["locator"]),
            )
            for item in raw_envelope.get("attachments", ())
        )
        actors = tuple(_construct(Actor, item) for item in raw_envelope.get("actors", ()))
        raw_time = raw_envelope["time"]
        time = _construct(
            TimeDeclaration,
            raw_time,
            execution_started_at=_construct(TimeValue, raw_time["execution_started_at"]),
            execution_finished_at=_construct(TimeValue, raw_time["execution_finished_at"]),
            artifact_created_at=(
                _construct(TimeValue, raw_time["artifact_created_at"])
                if raw_time.get("artifact_created_at") is not None
                else None
            ),
            adapted_at=(
                _construct(TimeValue, raw_time["adapted_at"])
                if raw_time.get("adapted_at") is not None
                else None
            ),
        )
        raw_privacy = raw_envelope["privacy"]
        privacy = _construct(
            PrivacyDeclaration,
            raw_privacy,
            declared_content_categories=tuple(raw_privacy.get("declared_content_categories", ())),
            transformations_applied=tuple(raw_privacy.get("transformations_applied", ())),
            validation=_construct(PrivacyValidation, raw_privacy["validation"], scope=tuple(raw_privacy["validation"].get("scope", ()))),
        )
        omissions = tuple(_construct(Omission, item) for item in raw_envelope.get("omissions", ()))
        capabilities = tuple(
            _construct(
                CapabilityClaim,
                item,
                requirements=tuple(
                    _construct(CapabilityRequirement, requirement)
                    for requirement in item.get("requirements", ())
                ),
                determinism=_construct(
                    DeterminismClaim,
                    item["determinism"],
                    conditions=tuple(item["determinism"].get("conditions", ())),
                ),
            )
            for item in raw_envelope.get("capabilities", ())
        )
        envelope = _construct(
            RecordEnvelope,
            raw_envelope,
            relationships=relationships,
            attachments=attachments,
            actors=actors,
            time=time,
            privacy=privacy,
            omissions=omissions,
            capabilities=capabilities,
        )
    except (KeyError, TypeError) as exc:
        raise ArtifactValidationError(f"invalid artifact envelope: {exc}") from exc
    return RunArtifact(envelope=envelope, body=dict(body))


def load_artifact(path: str | Path) -> RunArtifact:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return artifact_from_dict(payload)


def dump_artifact(artifact: RunArtifact, path: str | Path) -> None:
    Path(path).write_bytes(artifact_to_json_bytes(artifact))


def _digest_bytes(data: bytes, algorithm: str) -> str:
    if algorithm != "sha256":
        raise ArtifactValidationError(f"unsupported attachment digest algorithm: {algorithm}")
    return hashlib.sha256(data).hexdigest()


def _digest_file(path: Path, algorithm: str) -> str:
    if algorithm != "sha256":
        raise ArtifactValidationError(f"unsupported attachment digest algorithm: {algorithm}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _confined_bundle_path(root: Path, relative: str, *, label: str) -> Path:
    candidate = Path(relative)
    if candidate == Path(".") or candidate.is_absolute() or ".." in candidate.parts:
        raise ArtifactValidationError(f"{label} must be a confined bundle-relative path")
    resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ArtifactValidationError(f"{label} escapes the bundle root") from exc
    return resolved


def resolve_artifact_attachments(
    artifact: RunArtifact,
    bundle_root: str | Path,
) -> tuple[AttachmentResolution, ...]:
    """Resolve bundled-file attachments without allowing bundle-root escape."""

    root = Path(bundle_root).resolve()
    resolutions: list[AttachmentResolution] = []
    for attachment in artifact.envelope.attachments:
        locator = attachment.locator
        if attachment.declared_inclusion == "detached":
            resolutions.append(
                AttachmentResolution(
                    attachment_id=attachment.attachment_id,
                    status="unresolved",
                    declared_inclusion="detached",
                    requirement=attachment.requirement,
                    detail="intentionally detached from this bundle copy",
                )
            )
            continue
        if locator.type != "bundled-file" or locator.value is None:
            resolutions.append(
                AttachmentResolution(
                    attachment_id=attachment.attachment_id,
                    status="unresolved",
                    declared_inclusion=attachment.declared_inclusion,
                    requirement=attachment.requirement,
                    detail="attachment has no bundle-file locator",
                )
            )
            continue
        try:
            resolved = _confined_bundle_path(
                root,
                locator.value,
                label="bundle-file locator",
            )
        except ArtifactValidationError:
            resolutions.append(
                AttachmentResolution(
                    attachment_id=attachment.attachment_id,
                    status="unresolved",
                    declared_inclusion=attachment.declared_inclusion,
                    requirement=attachment.requirement,
                    detail="bundle-file locator escapes through a symbolic link",
                )
            )
            continue
        if not resolved.is_file():
            resolutions.append(
                AttachmentResolution(
                    attachment_id=attachment.attachment_id,
                    status="unresolved",
                    declared_inclusion=attachment.declared_inclusion,
                    requirement=attachment.requirement,
                    resolved_path=str(resolved),
                    detail="bundled file is absent or is not a regular file",
                )
            )
            continue
        try:
            actual_digest = _digest_file(resolved, locator.digest_algorithm)
        except ArtifactValidationError as exc:
            resolutions.append(
                AttachmentResolution(
                    attachment_id=attachment.attachment_id,
                    status="unresolved",
                    declared_inclusion=attachment.declared_inclusion,
                    requirement=attachment.requirement,
                    resolved_path=str(resolved),
                    detail=str(exc),
                )
            )
            continue
        if actual_digest != locator.digest:
            resolutions.append(
                AttachmentResolution(
                    attachment_id=attachment.attachment_id,
                    status="digest_mismatch",
                    declared_inclusion=attachment.declared_inclusion,
                    requirement=attachment.requirement,
                    resolved_path=str(resolved),
                    detail=f"expected {locator.digest_algorithm}:{locator.digest}",
                )
            )
            continue
        resolutions.append(
            AttachmentResolution(
                attachment_id=attachment.attachment_id,
                status="resolved",
                declared_inclusion=attachment.declared_inclusion,
                requirement=attachment.requirement,
                resolved_path=str(resolved),
            )
        )
    return tuple(resolutions)


def load_artifact_bundle(
    bundle_root: str | Path,
    *,
    artifact_filename: str = "record.json",
) -> ArtifactBundle:
    root = Path(bundle_root).resolve()
    artifact_path = _confined_bundle_path(
        root,
        artifact_filename,
        label="artifact filename",
    )
    artifact = load_artifact(artifact_path)
    return ArtifactBundle(
        artifact=artifact,
        resolutions=resolve_artifact_attachments(artifact, root),
        root=root,
    )


def write_artifact_bundle(
    artifact: RunArtifact,
    bundle_root: str | Path,
    attachment_bytes: Mapping[str, bytes],
    *,
    artifact_filename: str = "record.json",
) -> ArtifactBundle:
    """Atomically create a new confined bundle after validating exact bytes."""

    target = Path(bundle_root)
    if target.exists():
        raise FileExistsError(f"bundle target already exists: {target}")
    _confined_bundle_path(target.resolve(strict=False), artifact_filename, label="artifact filename")
    attachment_id_list = [item.attachment_id for item in artifact.envelope.attachments]
    attachment_ids = set(attachment_id_list)
    if len(attachment_id_list) != len(attachment_ids):
        raise ArtifactValidationError("attachment IDs must be unique for bundling")
    bundled_paths = [
        item.locator.value
        for item in artifact.envelope.attachments
        if item.declared_inclusion == "bundled"
    ]
    if len(bundled_paths) != len(set(bundled_paths)):
        raise ArtifactValidationError("bundled attachment paths must be unique")
    sensitivity_ids = set(artifact.envelope.privacy.reference_sensitivity)
    if sensitivity_ids != attachment_ids:
        raise ArtifactValidationError(
            "attachment IDs and privacy reference-sensitivity IDs must match for bundling"
        )
    extras = set(attachment_bytes) - attachment_ids
    if extras:
        raise ArtifactValidationError(f"bytes supplied for unknown attachments: {sorted(extras)}")

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=parent))
    try:
        (temporary / artifact_filename).parent.mkdir(parents=True, exist_ok=True)
        (temporary / artifact_filename).write_bytes(artifact_to_json_bytes(artifact))
        for attachment in artifact.envelope.attachments:
            if attachment.declared_inclusion == "detached":
                if attachment.attachment_id in attachment_bytes:
                    raise ArtifactValidationError(
                        f"bytes supplied for detached attachment: {attachment.attachment_id}"
                    )
                continue
            data = attachment_bytes.get(attachment.attachment_id)
            if data is None:
                raise ArtifactValidationError(
                    f"bundled attachment bytes are missing: {attachment.attachment_id}"
                )
            locator = attachment.locator
            if locator.type != "bundled-file" or locator.value is None:
                raise ArtifactValidationError(
                    f"bundled attachment requires a bundled-file locator: {attachment.attachment_id}"
                )
            if locator.value == artifact_filename:
                raise ArtifactValidationError(
                    f"attachment collides with root artifact file: {attachment.attachment_id}"
                )
            actual_digest = _digest_bytes(data, locator.digest_algorithm)
            if actual_digest != locator.digest:
                raise ArtifactValidationError(
                    f"attachment digest mismatch before write: {attachment.attachment_id}"
                )
            destination = temporary / str(locator.value)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        os.replace(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return load_artifact_bundle(target, artifact_filename=artifact_filename)


def summarize_artifact(artifact: RunArtifact) -> dict[str, Any]:
    """Expose common metadata without pretending to understand the body."""

    envelope = artifact.envelope
    return {
        "record_id": envelope.record_id,
        "kind": envelope.kind,
        "profile": envelope.profile,
        "lifecycle": envelope.lifecycle,
        "envelope_schema_version": envelope.envelope_schema_version,
        "body_version": envelope.body_version,
        "profile_version": envelope.profile_version,
        "relationships": len(envelope.relationships),
        "attachments": len(envelope.attachments),
        "privacy_validation": envelope.privacy.validation.status,
        "body_bytes_sensitivity": envelope.privacy.body_bytes_sensitivity,
        "capability_operations": [item.operation for item in envelope.capabilities],
        "body_interpretation": "not_evaluated",
    }
