from __future__ import annotations

import json
import hashlib
from pathlib import Path

from agent_lib import ToolResult
from examples.agent_command_isolation_probe import build_artifact, run_experiment
from llm_harness_core import artifact_to_dict


def _synthetic_runner(root, command, policy):
    if "container-created-marker" in command:
        (root / "container-created-marker").write_text("isolated", encoding="utf-8")
    return ToolResult(
        name="run_command",
        output="omitted",
        success=True,
        meta={
            "returncode": 0,
            "sandbox_backend": "docker",
            "sandbox_external": True,
            "sandbox_fallback_used": False,
            "sandbox_network_enabled": False,
        },
    )


def test_command_isolation_profile_passes_declared_gates(tmp_path):
    body = run_experiment(workspace_root=tmp_path / "workspace", runner=_synthetic_runner)
    assert body["case_count"] == 3
    assert body["acceptance_gate"]["external_docker_without_fallback"] is True
    assert body["acceptance_gate"]["case_semantics"] is True
    assert body["acceptance_gate"]["passed"] is True


def test_command_isolation_artifact_omits_commands_outputs_and_paths(tmp_path):
    body = run_experiment(workspace_root=tmp_path / "workspace", runner=_synthetic_runner)
    encoded = json.dumps(artifact_to_dict(build_artifact(body)))
    for forbidden in (str(tmp_path), "1.1.1.1", "/dev/tcp", "printf isolated", "host-only"):
        assert forbidden not in encoded


def test_committed_command_isolation_artifacts_are_pinned_and_private():
    root = Path(__file__).resolve().parents[1] / "docs" / "projects" / "agent_lib" / "runs"
    expected = {
        "2026-08-31-agent-command-isolation-v1.json": "ef6d5d2eb3745ce87d83898aef6abe46a0045b6db51f74abbec70529ee507386",
        "2026-08-31-agent-command-isolation-v2.json": "d78a0e6a94e1607a94be6f1c68b719f8a4c7b952aad484ed00d7e00b2b46904b",
    }
    for name, digest in expected.items():
        content = (root / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        decoded = content.decode()
        for forbidden in ("/home/", "/tmp/", "1.1.1.1", "/dev/tcp", "printf isolated"):
            assert forbidden not in decoded
