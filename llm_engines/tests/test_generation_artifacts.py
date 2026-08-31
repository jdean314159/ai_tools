from __future__ import annotations

from datetime import datetime, timezone

import pytest

from llm_harness_core import (
    PrivacyValidation,
    Relationship,
    artifact_from_dict,
    artifact_to_dict,
)
from llm_engines import (
    GenerationRecordingPolicy,
    RecordedGenerationError,
    build_generation_artifact,
    record_generation,
)
from llm_engines.backends.mock import MockEngine
from llm_engines.contracts import (
    ActiveInferenceOptimization,
    CacheStats,
    ChatMessage,
    GenerationRequest,
    ToolCall,
    UsageStats,
)


START = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 8, 13, 12, 0, 1, tzinfo=timezone.utc)


def _request(**updates) -> GenerationRequest:
    values = {
        "messages": [ChatMessage(role="user", content="Return the word fixture.")],
        "max_tokens": 16,
        "temperature": 0.0,
        "metadata": {"fixture": True},
    }
    values.update(updates)
    return GenerationRequest(**values)


def _response(request: GenerationRequest | None = None):
    return MockEngine(model="mock-fixture", latency_ms=1.5).generate(request or _request())


def _artifact(response=None, *, request=None, policy=None):
    return build_generation_artifact(
        request or _request(),
        response or _response(request),
        started_at=START,
        finished_at=END,
        record_id="rr_generation_fixture",
        requested_model="mock-fixture",
        engine_class="llm_engines.backends.mock.MockEngine",
        policy=policy or GenerationRecordingPolicy(usage_method="estimated"),
    )


def test_mock_generation_golden_contract_round_trips() -> None:
    artifact = _artifact()
    payload = artifact_to_dict(artifact)

    assert payload["envelope"]["kind"] == "generation"
    assert payload["envelope"]["lifecycle"] == "final"
    assert payload["envelope"]["time"]["execution_started_at"]["value"] == "2026-08-13T12:00:00Z"
    assert payload["body"]["request"]["messages"][0]["content"] == "Return the word fixture."
    assert payload["body"]["response"]["model_name"] == "mock-fixture"
    assert payload["body"]["model_identity"] == {
        "requested_label": "mock-fixture",
        "reported_label": "mock-fixture",
        "backend": "mock",
    }
    assert payload["body"]["provenance"]["/response/usage"]["method"] == "estimated"
    assert artifact_from_dict(payload) == artifact


def test_structured_output_and_truncation_remain_kind_specific() -> None:
    request = _request(json_schema={"type": "object", "properties": {"answer": {"type": "string"}}})
    response = _response(request).model_copy(
        update={
            "message": ChatMessage(role="assistant", content='{"answer":"fixture"}'),
            "finish_reason": "length",
        }
    )
    artifact = _artifact(response, request=request)

    assert artifact.body["request"]["json_schema"]["type"] == "object"
    assert artifact.body["response"]["finish_reason"] == "length"


def test_tool_call_is_preserved_in_generation_body() -> None:
    response = _response().model_copy(
        update={
            "message": ChatMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(call_id="call-1", name="lookup", arguments={"key": "fixture"})
                ],
            ),
            "finish_reason": "tool_call",
        }
    )

    artifact = _artifact(response)

    assert artifact.body["response"]["message"]["tool_calls"][0]["name"] == "lookup"


def test_partial_telemetry_is_omitted_not_zero() -> None:
    response = _response().model_copy(update={"usage": UsageStats()})
    artifact = _artifact(response)
    omissions = {item.field_path: item.reason for item in artifact.envelope.omissions}

    assert omissions["/body/response/usage/input_tokens"] == "not_reported_by_backend"
    assert omissions["/body/response/cache_stats"] == "not_reported_by_backend"
    assert artifact.body["response"]["usage"]["input_tokens"] is None
    assert omissions["/body/model_identity/digest"] == "not_reported_by_backend"


def test_reported_cache_and_optimization_metadata_are_preserved() -> None:
    response = _response().model_copy(
        update={
            "cache_stats": CacheStats(
                prompt_cache_hit_tokens=7, prompt_cache_miss_tokens=3, cache_key="fixture"
            ),
            "active_optimizations": [
                ActiveInferenceOptimization(
                    kind="other", backend="mock", parameters={"fixture": True}
                )
            ],
        }
    )
    artifact = _artifact(response)

    assert artifact.body["response"]["cache_stats"]["prompt_cache_hit_tokens"] == 7
    assert artifact.body["response"]["active_optimizations"][0]["kind"] == "other"
    assert "/body/response/cache_stats" not in {
        item.field_path for item in artifact.envelope.omissions
    }


def test_raw_payload_is_default_off_and_explicitly_includable() -> None:
    response = _response().model_copy(update={"raw_provider_payload": {"private": "fixture"}})
    redacted = _artifact(response)
    included = _artifact(
        response,
        policy=GenerationRecordingPolicy(
            include_raw_provider_payload=True,
            body_bytes_sensitivity="restricted",
        ),
    )

    assert "raw_provider_payload" not in redacted.body["response"]
    assert any(
        item.field_path == "/body/response/raw_provider_payload"
        and item.reason == "intentionally_not_recorded"
        for item in redacted.envelope.omissions
    )
    assert included.body["response"]["raw_provider_payload"] == {"private": "fixture"}


def test_record_generation_executes_engine_once_and_preserves_lineage() -> None:
    engine = MockEngine(model="mock-fixture")
    times = iter((START, END))
    relationship = Relationship(
        relation_type="part_of", target_kind="agent_run", target_id="rr_agent"
    )

    recorded = record_generation(
        engine,
        _request(),
        relationships=(relationship,),
        clock=lambda: next(times),
        record_id_factory=lambda: "rr_recorded",
    )

    assert engine.call_count == 1
    assert recorded.response.text == "Mock response to: Return the word fixture."
    assert recorded.response.model_name == "mock-fixture"
    assert recorded.artifact.envelope.relationships == (relationship,)


def test_failed_attempt_is_aborted_and_error_text_is_default_off() -> None:
    engine = MockEngine()
    times = iter((START, END))

    with pytest.raises(RecordedGenerationError) as caught:
        record_generation(
            engine,
            GenerationRequest(messages=[]),
            clock=lambda: next(times),
            record_id_factory=lambda: "rr_failed",
        )

    artifact = caught.value.artifact
    assert artifact.envelope.lifecycle == "aborted"
    assert artifact.body["outcome"] == "error"
    assert artifact.body["error"] == {"type": "GenerationError"}
    assert any(item.field_path == "/body/error/message" for item in artifact.envelope.omissions)


def test_privacy_validation_is_scoped_evidence_not_export_authorization() -> None:
    policy = GenerationRecordingPolicy(
        body_bytes_sensitivity="public",
        privacy_validation=PrivacyValidation(
            status="validated",
            validator="fixture-test",
            policy_id="safe-fixture",
            policy_version="1",
            validated_at="2026-08-13T12:00:01Z",
            scope=("fixed synthetic request and response",),
        ),
    )
    artifact = _artifact(policy=policy)

    assert artifact.envelope.privacy.validation.status == "validated"
    assert not hasattr(artifact.envelope.privacy, "exportable")
