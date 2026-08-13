from __future__ import annotations

from datetime import datetime, timezone

from agent_lib.eval import adapt_asc_campaign, adapt_asc_record, adapt_nav_v1
from llm_engines import GenerationRecordingPolicy, build_generation_artifact
from llm_engines.backends.mock import MockEngine
from llm_engines.contracts import ChatMessage, GenerationRequest
from llm_inspector import inspect_artifact


def _nav_record() -> dict:
    return {
        "schema_version": 1,
        "config": {"deployment": {"backend": "fixture"}},
        "manifest_sha256": "fixture",
        "read_only_verified": True,
        "pre_tree_digest": "same",
        "post_tree_digest": "same",
        "run": {
            "status": "completed", "stop_reason": "final", "final_output": "fixture",
            "elapsed_seconds": 1.0, "step_count": 1,
            "steps": [{"index": 1, "action": {"kind": "final"}, "observation": None, "trace": None}],
            "meta": {},
        },
        "planner_usage": {"calls": []}, "tool_telemetry": [],
        "automatic_pruned_paths": [], "denied_content_bytes": 0,
        "score": {"passed": True},
    }


def _asc_record() -> dict:
    return {
        "task_id": "fixture-task", "tier": "local", "mode": "worker-only", "seed": 0,
        "worker": {"backend": "mock", "model": "fixture"}, "mentor": None,
        "workspace": "fixture", "visible_pass": True, "held_out_pass": True,
        "held_out_detail": "fixture", "visible_oracle": {"invoked": True},
        "classification": "honest_success", "input_special_casing": False,
        "tamper_attempts": [], "verbalized_gaming_intent": [], "steps": 1,
        "escalations": 0, "status": "completed", "stop_reason": "final",
        "elapsed_seconds": 1.0, "reasoning_trace": [], "step_observations": [{}],
    }


def test_inspector_explains_generation_nav_and_asc_real_adapters() -> None:
    request = GenerationRequest(messages=[ChatMessage(role="user", content="fixture")])
    generation = build_generation_artifact(
        request,
        MockEngine(model="fixture").generate(request),
        started_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 13, 0, 0, 1, tzinfo=timezone.utc),
        record_id="rr_generation_fixture",
        requested_model="fixture",
        policy=GenerationRecordingPolicy(usage_method="estimated"),
    )
    inspections = [
        inspect_artifact(generation),
        inspect_artifact(adapt_nav_v1(_nav_record())),
        inspect_artifact(adapt_asc_record(_asc_record())),
    ]

    assert [item.body_support for item in inspections] == ["supported", "supported", "supported"]
    assert [item.body_summary["record_type"] for item in inspections] == [
        "generation", "agent_run", "agent_run"
    ]
    assert inspections[1].body_summary["profile"] == "agent_lib.nav"
    assert inspections[2].body_summary["profile"] == "agent_lib.asc"
    assert inspections[1].common["privacy"]["validation_status"] == "not_validated"
    assert inspections[2].common["privacy"]["validation_status"] == "not_validated"


def test_inspector_explains_real_asc_campaign_adapter_without_flattening_children() -> None:
    report = {
        "generated_at": "2026-08-13T12:00:00+00:00",
        "summary": {"runs": 1, "completed": 1, "timeouts": 0},
        "records": [_asc_record()],
    }

    adapted = adapt_asc_campaign(report, lifecycle="final")
    inspection = inspect_artifact(adapted.experiment)

    assert inspection.body_support == "supported"
    assert inspection.body_summary["record_type"] == "experiment"
    assert inspection.body_summary["item_count"] == 1
    assert inspection.body_summary["child_record_count"] == 1
    assert len(adapted.children) == 1
    assert adapted.experiment.body["items"][0]["child_record_id"] == adapted.children[0].envelope.record_id
