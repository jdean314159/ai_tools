from __future__ import annotations

from llm_harness_core import artifact_from_dict, artifact_to_dict

from agent_lib.eval.run_artifact_adapters import adapt_asc_record, adapt_nav_v1, restore_asc_record, restore_nav_v1


def _nav_record() -> dict:
    return {
        "schema_version": 1,
        "config": {"deployment": {"backend": "llama-server", "model_label": "fixture"}},
        "manifest_sha256": "manifest",
        "read_only_verified": True,
        "pre_tree_digest": "before",
        "post_tree_digest": "after",
        "run": {"status": "completed", "stop_reason": "final", "final_output": "fixture answer", "elapsed_seconds": 1.25, "step_count": 1, "steps": [{"index": 1, "action": {"kind": "final"}, "observation": None, "trace": None}], "meta": {"fixture": True}},
        "planner_usage": {"calls": [{"actual_total_tokens": 4}]},
        "tool_telemetry": [],
        "automatic_pruned_paths": [],
        "denied_content_bytes": 0,
        "score": {"passed": True},
    }


def _asc_record() -> dict:
    return {
        "task_id": "gaming_square", "tier": "gaming-tempting", "mode": "worker-only", "seed": 0,
        "worker": {"backend": "ollama", "model": "fixture", "quantization": "Q4", "think": True},
        "mentor": None, "workspace": "fixture/workspace", "visible_pass": True,
        "held_out_pass": False, "held_out_detail": "fixture", "visible_oracle": {"invoked": True},
        "classification": "gaming", "input_special_casing": True, "tamper_attempts": [],
        "verbalized_gaming_intent": [], "steps": 1, "escalations": 0, "status": "completed",
        "stop_reason": "final", "elapsed_seconds": 2.0, "reasoning_trace": ["fixture reasoning"],
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
