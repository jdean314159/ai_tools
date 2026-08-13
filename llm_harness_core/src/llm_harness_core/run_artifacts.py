"""Dependency-free contracts for durable LLM run artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
from pathlib import Path
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
    Path(path).write_text(
        json.dumps(artifact_to_dict(artifact), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
