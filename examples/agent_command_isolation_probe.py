"""Frozen, privacy-bounded validation of agent_lib container command isolation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import tempfile
from typing import Any, Callable

from agent_lib import WorkspacePolicy
from agent_lib.programming import execute_workspace_command
from llm_harness_core import (
    Actor, CapabilityClaim, CapabilityRequirement, DeterminismClaim,
    PrivacyDeclaration, PrivacyValidation, RecordEnvelope, RunArtifact,
    TimeDeclaration, TimeValue, dump_artifact, prepare_new_artifact_path,
)


PROFILE = "agent_lib.command_isolation"
PROFILE_VERSION = 2
DEFAULT_IMAGE = "nvidia/cuda:12.4.0-base-ubuntu22.04"
CASE_IDS = ("workspace_write", "host_escape_blocked", "network_blocked")
Runner = Callable[[Path, str, WorkspacePolicy], Any]


def suite_digest() -> str:
    frozen = {
        "profile_version": PROFILE_VERSION,
        "cases": CASE_IDS,
        "backend": "docker",
        "network": False,
        "fallback_to_host": False,
    }
    raw = json.dumps(frozen, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _execute(root: Path, command: str, policy: WorkspacePolicy) -> Any:
    return execute_workspace_command(root, command, workspace_policy=policy)


def run_experiment(*, workspace_root: Path, image: str = DEFAULT_IMAGE, runner: Runner = _execute) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    workspace_root.mkdir(parents=True, exist_ok=True)
    host_marker = workspace_root.parent / "agent-lib-host-only-marker"
    host_marker.write_text("host-only\n", encoding="utf-8")
    workspace_marker = workspace_root / "container-created-marker"
    commands = {
        "workspace_write": "printf isolated > container-created-marker",
        "host_escape_blocked": f"test ! -e {shlex.quote(str(host_marker))}",
        "network_blocked": (
            "if timeout 2 bash -c 'echo probe > /dev/tcp/1.1.1.1/53' 2>/dev/null; "
            "then exit 9; else exit 0; fi"
        ),
    }
    observations: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        command = commands[case_id]
        policy = WorkspacePolicy(
            root=str(workspace_root), runnable_commands=[command],
            command_timeout_seconds=8.0, command_isolation_backend="docker",
            command_isolation_image=image, command_isolation_network=False,
            command_isolation_fallback_to_host=False,
        )
        result = runner(workspace_root, command, policy)
        semantic_pass = bool(result.success)
        if case_id == "workspace_write":
            semantic_pass = semantic_pass and workspace_marker.read_text(encoding="utf-8") == "isolated"
        observations.append({
            "case_id": case_id,
            "tool_success": bool(result.success),
            "semantic_pass": semantic_pass,
            "error": result.meta.get("error"),
            "returncode": result.meta.get("returncode"),
            "sandbox_backend": result.meta.get("sandbox_backend"),
            "sandbox_external": result.meta.get("sandbox_external"),
            "sandbox_fallback_used": result.meta.get("sandbox_fallback_used"),
            "network_enabled": result.meta.get("sandbox_network_enabled"),
        })
    host_marker_unchanged = host_marker.read_text(encoding="utf-8") == "host-only\n"
    external_docker = all(
        item["sandbox_backend"] == "docker"
        and item["sandbox_external"] is True
        and item["sandbox_fallback_used"] is False
        for item in observations
    )
    semantics_pass = all(item["semantic_pass"] for item in observations) and host_marker_unchanged
    finished = datetime.now(timezone.utc)
    return {
        "schema_version": 1, "profile": PROFILE, "profile_version": PROFILE_VERSION,
        "suite_digest": suite_digest(),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "case_count": len(observations), "runtime_backend": "docker",
        "image_label": image, "observations": observations,
        "acceptance_gate": {
            "require_external_docker_without_fallback": True,
            "require_case_semantics": True,
            "external_docker_without_fallback": external_docker,
            "case_semantics": semantics_pass,
            "passed": external_docker and semantics_pass,
        },
        "privacy": {
            "raw_commands_retained": False, "raw_outputs_retained": False,
            "workspace_paths_retained": False, "environment_values_retained": False,
        },
        "interpretation_limit": (
            "Three local Docker cases validate one workspace write, host-marker invisibility, and "
            "default network denial; not a general container escape, resource-limit, or daemon-security audit."
        ),
    }


def build_artifact(body: dict[str, Any]) -> RunArtifact:
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    finished = body["finished_at"]
    return RunArtifact(RecordEnvelope(
        kind="experiment", envelope_schema_version=1, body_version=1,
        profile=PROFILE, profile_version=PROFILE_VERSION,
        record_id=f"ci_{digest[:32]}", lifecycle="final", relationships=(), attachments=(),
        actors=(Actor("command-isolation-runner", "recorder", PROFILE, "1"),),
        time=TimeDeclaration(
            TimeValue("value", body["started_at"], "runner"),
            TimeValue("value", finished, "runner"), TimeValue("value", finished, "runner"),
        ),
        privacy=PrivacyDeclaration(
            declared_content_categories=("synthetic_command",),
            body_bytes_sensitivity="low; commands, outputs, paths, and environment values omitted",
            transformations_applied=({"operation": "retain_outcomes_and_isolation_metadata_only", "version": "1"},),
            validation=PrivacyValidation(
                "validated", ("no raw commands, output, workspace paths, or environment values",),
                PROFILE, "synthetic-isolation-no-raw-content", "1", finished,
            ),
        ),
        capabilities=(CapabilityClaim(
            "container_command_isolation",
            (CapabilityRequirement("implementation", "agent_lib"),
             CapabilityRequirement("external_service", "docker_daemon")),
            "local_compute", "state_changing",
            DeterminismClaim("best_effort", "exercised", ("cached image", "network disabled")), "1",
        ),),
        execution_environment={"runtime_backend": body["runtime_backend"], "image_label": body["image_label"]},
    ), body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    args = parser.parse_args(argv)
    target = prepare_new_artifact_path(args.artifact)
    with tempfile.TemporaryDirectory(prefix="agent-command-isolation-") as tmp:
        body = run_experiment(workspace_root=Path(tmp) / "workspace", image=args.image)
    dump_artifact(build_artifact(body), target)
    print(json.dumps({key: value for key, value in body.items() if key != "observations"}, indent=2, sort_keys=True))
    return 0 if body["acceptance_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
