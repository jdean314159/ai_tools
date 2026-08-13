from __future__ import annotations

from datetime import datetime, timezone

from agent_lib.eval import adapt_nav_v1
from llm_engines import build_generation_artifact
from llm_engines.backends.mock import MockEngine
from llm_engines.contracts import ChatMessage, GenerationRequest
from llm_harness_core import (
    Relationship,
    SupportedBodyContract,
    artifact_from_dict,
    artifact_to_dict,
    body_support_status,
    summarize_artifact,
)


def _nav_record() -> dict:
    return {
        "schema_version": 1,
        "config": {"deployment": {"backend": "fixture"}},
        "manifest_sha256": "fixture-manifest",
        "read_only_verified": True,
        "pre_tree_digest": "same",
        "post_tree_digest": "same",
        "run": {
            "status": "completed",
            "stop_reason": "final",
            "final_output": "fixture",
            "elapsed_seconds": 1.0,
            "step_count": 1,
            "steps": [{"index": 1, "action": {"kind": "final"}, "observation": None, "trace": None}],
            "meta": {},
        },
        "planner_usage": {"calls": []},
        "tool_telemetry": [],
        "automatic_pruned_paths": [],
        "denied_content_bytes": 0,
        "score": {"passed": True},
    }


def test_common_reader_handles_agent_and_generation_without_homogenizing_bodies() -> None:
    agent = adapt_nav_v1(_nav_record())
    request = GenerationRequest(messages=[ChatMessage(role="user", content="fixture")])
    response = MockEngine(model="mock-fixture").generate(request)
    generation = build_generation_artifact(
        request,
        response,
        started_at=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 13, 12, 0, 1, tzinfo=timezone.utc),
        record_id="rr_generation",
        requested_model="mock-fixture",
        relationships=(
            Relationship(
                relation_type="part_of",
                target_kind="agent_run",
                target_id=agent.envelope.record_id,
            ),
        ),
    )
    supported = (
        SupportedBodyContract(
            kind="agent_run",
            body_version=1,
            profile="agent_lib.nav",
            profile_version=1,
        ),
        SupportedBodyContract(kind="generation", body_version=1),
    )

    parsed_agent = artifact_from_dict(artifact_to_dict(agent))
    parsed_generation = artifact_from_dict(artifact_to_dict(generation))

    assert body_support_status(parsed_agent, supported) == "supported"
    assert body_support_status(parsed_generation, supported) == "supported"
    assert summarize_artifact(parsed_agent)["kind"] == "agent_run"
    assert summarize_artifact(parsed_generation)["kind"] == "generation"
    assert "steps" in parsed_agent.body and "request" not in parsed_agent.body
    assert "request" in parsed_generation.body and "steps" not in parsed_generation.body
    assert parsed_generation.envelope.relationships[0].target_id == agent.envelope.record_id
    assert parsed_generation.envelope.attachments == ()


def test_detached_semantic_relationship_does_not_become_missing_attachment() -> None:
    agent = adapt_nav_v1(_nav_record())
    request = GenerationRequest(messages=[ChatMessage(role="user", content="fixture")])
    generation = build_generation_artifact(
        request,
        MockEngine().generate(request),
        started_at=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 13, 12, 0, 1, tzinfo=timezone.utc),
        record_id="rr_detached_generation",
        relationships=(
            Relationship(
                relation_type="part_of",
                target_kind="agent_run",
                target_id=agent.envelope.record_id,
            ),
        ),
    )

    copied_without_parent = artifact_from_dict(artifact_to_dict(generation))

    assert copied_without_parent.envelope.relationships[0].target_id == agent.envelope.record_id
    assert copied_without_parent.envelope.attachments == ()
