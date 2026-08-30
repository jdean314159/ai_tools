from __future__ import annotations

import json
import hashlib
from pathlib import Path

from examples.agent_policy_observability_probe import run_experiment


def test_policy_observability_profile_exposes_the_frozen_outcomes(tmp_path):
    body = run_experiment(workspace_root=tmp_path)

    assert body["case_count"] == 6
    assert body["acceptance_gate"]["expected_policy_outcomes"] is True
    assert body["acceptance_gate"]["common_trace_events"] is True
    assert body["acceptance_gate"]["signal_parity"] is True
    assert body["acceptance_gate"]["passed"] is True
    outcomes = {item["case_id"]: item for item in body["observations"]}
    assert outcomes["tool_not_granted"]["signal_complete"] is True
    assert outcomes["path_escape"]["signal_complete"] is True
    assert outcomes["write_denied"]["signal_complete"] is True
    assert outcomes["command_denied"]["signal_complete"] is True
    assert outcomes["approval_required"]["signal_complete"] is True
    assert outcomes["objective_failure"]["signal_complete"] is True


def test_policy_observability_artifact_is_privacy_minimized(tmp_path):
    encoded = json.dumps(run_experiment(workspace_root=tmp_path))
    assert str(tmp_path) not in encoded
    for forbidden in ("../outside.txt", "echo denied", "synthetic mismatch"):
        assert forbidden not in encoded


def test_committed_policy_observability_artifacts_are_pinned_and_private():
    root = Path(__file__).resolve().parents[1] / "docs" / "projects" / "agent_lib" / "runs"
    expected = {
        "2026-08-30-agent-policy-observability-v1.json":
            "b65b2591202221b13c341e293d4525d0a92b73e912c8f2ce1af2451056c9b063",
        "2026-08-30-agent-policy-observability-v2.json":
            "3044149abef32e2abc9fbbca7f9ba329d67e367451bdc864e5173d8e6465cc85",
    }
    for name, digest in expected.items():
        content = (root / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        decoded = content.decode()
        for forbidden in ("/tmp/", "/home/", "../outside.txt", "synthetic mismatch"):
            assert forbidden not in decoded
