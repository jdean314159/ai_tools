from __future__ import annotations

from llm_harness_core import artifact_from_dict, artifact_to_dict, load_artifact_bundle

from agent_lib.eval.run_artifact_adapters import (
    adapt_asc_campaign,
    adapt_asc_record,
    adapt_nav_campaign,
    adapt_nav_v1,
    prepare_experiment_bundle,
    restore_asc_record,
    restore_nav_v1,
    write_experiment_bundle,
)


def _nav_record() -> dict:
    return {
        "schema_version": 1,
        "config": {"deployment": {"backend": "llama-server", "model_label": "fixture"}},
        "manifest_sha256": "manifest",
        "read_only_verified": True,
        "pre_tree_digest": "before",
        "post_tree_digest": "after",
        "run": {
            "status": "completed",
            "stop_reason": "final",
            "final_output": "fixture answer",
            "elapsed_seconds": 1.25,
            "step_count": 1,
            "steps": [
                {"index": 1, "action": {"kind": "final"}, "observation": None, "trace": None}
            ],
            "meta": {"fixture": True},
        },
        "planner_usage": {"calls": [{"actual_total_tokens": 4}]},
        "tool_telemetry": [],
        "automatic_pruned_paths": [],
        "denied_content_bytes": 0,
        "score": {"passed": True},
    }


def _asc_record() -> dict:
    return {
        "task_id": "gaming_square",
        "tier": "gaming-tempting",
        "mode": "worker-only",
        "seed": 0,
        "worker": {"backend": "ollama", "model": "fixture", "quantization": "Q4", "think": True},
        "mentor": None,
        "workspace": "fixture/workspace",
        "visible_pass": True,
        "held_out_pass": False,
        "held_out_detail": "fixture",
        "visible_oracle": {"invoked": True},
        "classification": "gaming",
        "input_special_casing": True,
        "tamper_attempts": [],
        "verbalized_gaming_intent": [],
        "steps": 1,
        "escalations": 0,
        "status": "completed",
        "stop_reason": "final",
        "elapsed_seconds": 2.0,
        "reasoning_trace": ["fixture reasoning"],
        "step_observations": [{"kind": "tool"}],
    }


def test_nav_adapter_is_stable_lossless_and_keeps_steps_inline() -> None:
    source = _nav_record()
    first = adapt_nav_v1(source)
    second = adapt_nav_v1(source)
    assert first.envelope.kind == "agent_run"
    assert first.envelope.profile == "agent_lib.nav"
    assert first.envelope.record_id == second.envelope.record_id
    assert first.body["steps"] == source["run"]["steps"]
    assert restore_nav_v1(first) == source
    assert artifact_from_dict(artifact_to_dict(first)) == first


def test_asc_adapter_shares_agent_body_and_is_lossless() -> None:
    source = _asc_record()
    artifact = adapt_asc_record(source)
    assert artifact.envelope.kind == "agent_run"
    assert artifact.envelope.profile == "agent_lib.asc"
    assert set(("task", "status", "steps", "model_roles", "evaluation")) <= artifact.body.keys()
    assert restore_asc_record(artifact) == source
    assert artifact_from_dict(artifact_to_dict(artifact)) == artifact


def test_legacy_privacy_is_conservative() -> None:
    artifact = adapt_nav_v1(_nav_record())
    assert artifact.envelope.privacy.body_bytes_sensitivity == "unknown"
    assert artifact.envelope.privacy.validation.status == "not_validated"


def test_asc_campaign_separates_published_children_from_timeout_items() -> None:
    completed = _asc_record()
    timeout = {
        **_asc_record(),
        "task_id": "timeout_task",
        "status": "timeout",
        "classification": "timeout",
        "step_observations": [],
    }
    report = {
        "generated_at": "2026-08-13T12:00:00+00:00",
        "summary": {"runs": 2, "completed": 1, "timeouts": 1},
        "records": [completed, timeout],
    }

    adapted = adapt_asc_campaign(report, lifecycle="checkpoint")

    assert adapted.experiment.envelope.kind == "experiment"
    assert adapted.experiment.envelope.lifecycle == "checkpoint"
    assert len(adapted.children) == 1
    assert len(adapted.experiment.body["items"]) == 2
    timeout_item = adapted.experiment.body["items"][1]
    assert timeout_item["status"] == "timeout"
    assert timeout_item["child_record_id"] is None
    assert "step_observations" not in timeout_item
    child_id = adapted.children[0].envelope.record_id
    assert adapted.experiment.body["items"][0]["child_record_id"] == child_id
    assert any(r.target_id == child_id for r in adapted.experiment.envelope.relationships)
    assert artifact_from_dict(artifact_to_dict(adapted.experiment)) == adapted.experiment


def test_asc_campaign_requires_caller_to_declare_lifecycle() -> None:
    report = {"summary": {"runs": 0}, "records": []}

    try:
        adapt_asc_campaign(report, lifecycle="inferred")
    except ValueError as exc:
        assert "lifecycle" in str(exc)
    else:
        raise AssertionError("invalid lifecycle was accepted")


def test_nav_campaign_checkpoint_and_final_have_honest_child_references() -> None:
    pairs = [
        {
            "task_id": "fixture-task",
            "tier": "local",
            "no_ledger": {"exact_correct": False, "tokens": 10},
            "ledger": {"exact_correct": True, "tokens": 12},
        }
    ]
    no_ledger = _nav_record()
    no_ledger["config"]["mode"] = "no_ledger"
    ledger = _nav_record()
    ledger["config"]["mode"] = "ledger"

    checkpoint = adapt_nav_campaign(pairs)
    final = adapt_nav_campaign(
        pairs,
        summary={"pair_count": 1},
        decision={"verdict": "continue"},
        arm_records={
            ("fixture-task", "no_ledger"): no_ledger,
            ("fixture-task", "ledger"): ledger,
        },
    )

    assert checkpoint.experiment.envelope.lifecycle == "checkpoint"
    assert checkpoint.children == ()
    assert final.experiment.envelope.lifecycle == "final"
    assert len(final.children) == 2
    assert final.experiment.body["aggregate"] == {"pair_count": 1}
    assert final.experiment.body["decision"] == {"verdict": "continue"}
    arm_summaries = final.experiment.body["items"][0]["arms"]
    assert arm_summaries["no_ledger"]["child_record_id"]
    assert arm_summaries["ledger"]["child_record_id"]
    assert "run" not in arm_summaries["ledger"]
    assert final.experiment.envelope.record_id != checkpoint.experiment.envelope.record_id


def test_nav_campaign_rejects_half_final_state() -> None:
    try:
        adapt_nav_campaign([], summary={"pair_count": 0})
    except ValueError as exc:
        assert "together" in str(exc)
    else:
        raise AssertionError("half-final campaign was accepted")


def test_campaign_adapters_reject_ambiguous_or_unrelated_children() -> None:
    asc_record = _asc_record()
    try:
        adapt_asc_campaign(
            {"summary": {"runs": 2}, "records": [asc_record, asc_record]},
            lifecycle="checkpoint",
        )
    except ValueError as exc:
        assert "duplicate ASC" in str(exc)
    else:
        raise AssertionError("duplicate ASC campaign item was accepted")

    try:
        adapt_nav_campaign(
            [],
            arm_records={("not-in-campaign", "ledger"): _nav_record()},
        )
    except ValueError as exc:
        assert "do not belong" in str(exc)
    else:
        raise AssertionError("unrelated NAV arm artifact was accepted")


def test_experiment_bundle_is_a_new_derived_snapshot_with_exact_child_bytes() -> None:
    report = {
        "summary": {"runs": 1, "completed": 1},
        "records": [_asc_record()],
    }
    adaptation = adapt_asc_campaign(report, lifecycle="final")

    prepared = prepare_experiment_bundle(adaptation)

    assert prepared.artifact.envelope.record_id != adaptation.experiment.envelope.record_id
    assert adaptation.experiment.envelope.attachments == ()
    assert len(prepared.artifact.envelope.attachments) == 1
    attachment = prepared.artifact.envelope.attachments[0]
    assert attachment.logical_role == "child_run_artifact"
    assert attachment.declared_inclusion == "bundled"
    assert attachment.requirement == "optional"
    assert attachment.locator.value.startswith("children/")
    assert attachment.attachment_id in prepared.attachment_bytes
    assert (
        prepared.artifact.envelope.privacy.reference_sensitivity[attachment.attachment_id]
        == "unknown"
    )
    assert any(
        relationship.relation_type == "derived_from"
        and relationship.target_id == adaptation.experiment.envelope.record_id
        for relationship in prepared.artifact.envelope.relationships
    )


def test_write_experiment_bundle_resolves_then_detects_tampering(tmp_path) -> None:
    adaptation = adapt_asc_campaign(
        {"summary": {"runs": 1}, "records": [_asc_record()]},
        lifecycle="final",
    )
    root = tmp_path / "campaign-bundle"

    bundle = write_experiment_bundle(adaptation, str(root))

    assert bundle.artifact.envelope.kind == "experiment"
    assert [result.status for result in bundle.resolutions] == ["resolved"]
    child_path = root / bundle.artifact.envelope.attachments[0].locator.value
    child_path.write_text("tampered", encoding="utf-8")
    reloaded = load_artifact_bundle(root)
    assert [result.status for result in reloaded.resolutions] == ["digest_mismatch"]
