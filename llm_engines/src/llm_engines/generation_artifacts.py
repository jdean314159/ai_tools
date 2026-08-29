"""Durable artifact recording around the existing generation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Mapping
from uuid import uuid4

from llm_harness_core import (
    Actor,
    Omission,
    PrivacyDeclaration,
    PrivacyValidation,
    RecordEnvelope,
    Relationship,
    RunArtifact,
    TimeDeclaration,
    TimeValue,
)

from .contracts import ChatModel, GenerationRequest, GenerationResponse


GENERATION_BODY_VERSION = 1
RECORDER_VERSION = "1"


@dataclass(frozen=True)
class GenerationRecordingPolicy:
    """Persistence choices that must be explicit at the recording boundary."""

    include_raw_provider_payload: bool = False
    include_error_message: bool = False
    body_bytes_sensitivity: str = "restricted"
    declared_content_categories: tuple[str, ...] = (
        "model_input",
        "model_output",
    )
    transformations_applied: tuple[Mapping[str, Any], ...] = ()
    privacy_validation: PrivacyValidation = PrivacyValidation(status="not_validated")
    usage_method: Literal["measured", "estimated", "declared"] = "declared"


@dataclass(frozen=True)
class RecordedGeneration:
    response: GenerationResponse
    artifact: RunArtifact


class RecordedGenerationError(Exception):
    """A generation failure accompanied by its durable attempt artifact."""

    def __init__(self, cause: Exception, artifact: RunArtifact) -> None:
        super().__init__(f"recorded generation failed: {type(cause).__name__}")
        self.cause = cause
        self.artifact = artifact


Clock = Callable[[], datetime]
RecordIdFactory = Callable[[], str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_record_id() -> str:
    return f"rr_{uuid4().hex}"


def _timestamp(value: datetime) -> TimeValue:
    if value.tzinfo is None:
        raise ValueError("generation artifact clock must return timezone-aware datetimes")
    return TimeValue(
        status="value",
        value=value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        source="llm_engines.generation_artifacts",
        precision="microsecond",
    )


def _privacy(policy: GenerationRecordingPolicy) -> PrivacyDeclaration:
    return PrivacyDeclaration(
        declared_content_categories=policy.declared_content_categories,
        body_bytes_sensitivity=policy.body_bytes_sensitivity,
        transformations_applied=policy.transformations_applied,
        validation=policy.privacy_validation,
    )


def _usage_omissions(response: GenerationResponse | None) -> list[Omission]:
    omissions: list[Omission] = []
    if response is None:
        return omissions
    for field_name in ("input_tokens", "output_tokens", "total_tokens", "latency_ms"):
        if getattr(response.usage, field_name) is None:
            omissions.append(
                Omission(
                    field_path=f"/body/response/usage/{field_name}",
                    reason="not_reported_by_backend",
                )
            )
    cache = response.cache_stats
    if (
        cache.prompt_cache_hit_tokens == 0
        and cache.prompt_cache_miss_tokens == 0
        and cache.cache_key is None
    ):
        omissions.append(
            Omission(
                field_path="/body/response/cache_stats",
                reason="not_reported_by_backend",
            )
        )
    return omissions


def _envelope(
    *,
    record_id: str,
    started: datetime,
    finished: datetime,
    engine_name: str,
    policy: GenerationRecordingPolicy,
    omissions: tuple[Omission, ...],
    relationships: tuple[Relationship, ...],
    execution_environment: Mapping[str, Any],
    lifecycle: str,
) -> RecordEnvelope:
    return RecordEnvelope(
        kind="generation",
        envelope_schema_version=1,
        body_version=GENERATION_BODY_VERSION,
        record_id=record_id,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        profile=None,
        profile_version=None,
        relationships=relationships,
        attachments=(),
        actors=(
            Actor(
                actor_id="engine",
                role="original_producer",
                name=engine_name,
            ),
            Actor(
                actor_id="recorder",
                role="recorder",
                name="llm_engines.generation_artifacts",
                version=RECORDER_VERSION,
            ),
        ),
        time=TimeDeclaration(
            execution_started_at=_timestamp(started),
            execution_finished_at=_timestamp(finished),
            artifact_created_at=_timestamp(finished),
        ),
        privacy=_privacy(policy),
        omissions=omissions,
        capabilities=(),
        execution_environment=dict(execution_environment),
    )


def build_generation_artifact(
    request: GenerationRequest,
    response: GenerationResponse,
    *,
    started_at: datetime,
    finished_at: datetime,
    record_id: str,
    policy: GenerationRecordingPolicy | None = None,
    relationships: tuple[Relationship, ...] = (),
    engine_class: str | None = None,
    requested_model: str | None = None,
) -> RunArtifact:
    """Build a final artifact from an already completed runtime response."""

    policy = policy or GenerationRecordingPolicy()
    response_payload = response.model_dump(mode="json")
    raw_payload = response_payload.pop("raw_provider_payload", None)
    omissions = _usage_omissions(response)
    omissions.extend(
        Omission(field_path=path, reason="not_reported_by_backend")
        for path in (
            "/body/model_identity/digest",
            "/body/model_identity/quantization",
            "/envelope/execution_environment/runtime_build",
            "/envelope/execution_environment/tokenizer",
            "/envelope/execution_environment/chat_template",
            "/body/response/usage/queue_ms",
            "/body/response/usage/prefill_ms",
        )
    )
    if raw_payload is not None:
        if policy.include_raw_provider_payload:
            response_payload["raw_provider_payload"] = raw_payload
        else:
            omissions.append(
                Omission(
                    field_path="/body/response/raw_provider_payload",
                    reason="intentionally_not_recorded",
                )
            )
    else:
        omissions.append(
            Omission(
                field_path="/body/response/raw_provider_payload",
                reason="not_reported_by_backend",
            )
        )
    body = {
        "outcome": "completed",
        "request": request.model_dump(mode="json"),
        "response": response_payload,
        "model_identity": {
            "requested_label": requested_model,
            "reported_label": response.model_name,
            "backend": response.backend,
        },
        "provenance": {
            "/response/usage": {"method": policy.usage_method, "supplied_by": "engine"},
            "/request": {"method": "copied", "supplied_by": "recorder"},
        },
    }
    if requested_model is None:
        omissions.append(
            Omission(
                field_path="/body/model_identity/requested_label",
                reason="absent_in_source_format",
            )
        )
    environment = {
        "backend": response.backend,
        "engine_class": engine_class,
    }
    return RunArtifact(
        envelope=_envelope(
            record_id=record_id,
            started=started_at,
            finished=finished_at,
            engine_name=response.backend,
            policy=policy,
            omissions=tuple(omissions),
            relationships=relationships,
            execution_environment=environment,
            lifecycle="final",
        ),
        body=body,
    )


def build_generation_failure_artifact(
    request: GenerationRequest,
    error: Exception,
    *,
    started_at: datetime,
    finished_at: datetime,
    record_id: str,
    policy: GenerationRecordingPolicy | None = None,
    relationships: tuple[Relationship, ...] = (),
    engine_class: str,
    requested_model: str | None = None,
) -> RunArtifact:
    """Build an immutable aborted attempt without leaking error text by default."""

    policy = policy or GenerationRecordingPolicy()
    error_payload: dict[str, Any] = {"type": type(error).__name__}
    omissions = [
        Omission(field_path="/body/response", reason="capture_failed"),
        Omission(field_path="/body/error/message", reason="intentionally_not_recorded"),
    ]
    if policy.include_error_message:
        error_payload["message"] = str(error)
        omissions.pop()
    body = {
        "outcome": "error",
        "request": request.model_dump(mode="json"),
        "response": None,
        "error": error_payload,
        "model_identity": {
            "requested_label": requested_model,
            "reported_label": None,
            "backend": None,
        },
        "provenance": {
            "/request": {"method": "copied", "supplied_by": "recorder"},
            "/error/type": {"method": "measured", "supplied_by": "recorder"},
        },
    }
    return RunArtifact(
        envelope=_envelope(
            record_id=record_id,
            started=started_at,
            finished=finished_at,
            engine_name=engine_class,
            policy=policy,
            omissions=tuple(omissions),
            relationships=relationships,
            execution_environment={"engine_class": engine_class},
            lifecycle="aborted",
        ),
        body=body,
    )


def record_generation(
    engine: ChatModel,
    request: GenerationRequest,
    *,
    policy: GenerationRecordingPolicy | None = None,
    relationships: tuple[Relationship, ...] = (),
    clock: Clock = _utc_now,
    record_id_factory: RecordIdFactory = _new_record_id,
) -> RecordedGeneration:
    """Execute one engine call and record its success or failure exactly once."""

    started = clock()
    record_id = record_id_factory()
    engine_class = f"{type(engine).__module__}.{type(engine).__qualname__}"
    requested_model = getattr(engine, "model", None)
    if requested_model is not None:
        requested_model = str(requested_model)
    try:
        response = engine.generate(request)
    except Exception as exc:
        artifact = build_generation_failure_artifact(
            request,
            exc,
            started_at=started,
            finished_at=clock(),
            record_id=record_id,
            policy=policy,
            relationships=relationships,
            engine_class=engine_class,
            requested_model=requested_model,
        )
        raise RecordedGenerationError(exc, artifact) from exc
    artifact = build_generation_artifact(
        request,
        response,
        started_at=started,
        finished_at=clock(),
        record_id=record_id,
        policy=policy,
        relationships=relationships,
        engine_class=engine_class,
        requested_model=requested_model,
    )
    return RecordedGeneration(response=response, artifact=artifact)
