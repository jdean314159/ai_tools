from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING, Any

from ..contracts import AgentRun
from .navigation_workspace import NavigationPolicy, NavigationWorkspace

if TYPE_CHECKING:
    from .repo_navigation import NavigationHarness


def _git_value(root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def build_environment_manifest(policy: NavigationPolicy) -> dict[str, Any]:
    workspace = NavigationWorkspace(policy)
    allowed, pruned = workspace._walk_source_files(policy.root, "*")
    allowed_records = []
    for path in sorted(allowed):
        data, denied = workspace._read_source_bytes(path)
        if data is None:
            pruned += 1
            continue
        allowed_records.append(
            {
                "path": workspace._relative(path),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    denied_count = 0
    denied_bytes = 0
    total_count = 0
    total_bytes = 0
    for directory, dirnames, filenames in os.walk(policy.root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            path = directory_path / name
            try:
                size = path.stat().st_size
                relative = workspace._relative(path.resolve(strict=True))
            except (OSError, ValueError):
                continue
            total_count += 1
            total_bytes += size
            oversized_json = path.suffix.lower() == ".json" and size > policy.max_json_bytes
            if (
                workspace._denied_relative(relative)
                or path.suffix.lower() not in policy.source_suffixes
                or size > policy.max_file_bytes
                or oversized_json
            ):
                denied_count += 1
                denied_bytes += size
    payload = {
        "schema_version": 1,
        "root_name": policy.root.name,
        "git_sha": _git_value(policy.root, "rev-parse", "HEAD"),
        "git_status_porcelain": _git_value(policy.root, "status", "--porcelain"),
        "measurement": {
            "implementation": "agent_lib.eval.repo_navigation.build_environment_manifest",
            "git_commands": ["git rev-parse HEAD", "git status --porcelain"],
        },
        "policy": {
            **asdict(policy),
            "root": str(policy.root),
            "denied_directory_names": sorted(policy.denied_directory_names),
            "denied_suffixes": sorted(policy.denied_suffixes),
            "source_suffixes": sorted(policy.source_suffixes),
        },
        "totals": {
            "files": total_count,
            "bytes": total_bytes,
            "allowed_files": len(allowed_records),
            "allowed_bytes": sum(item["bytes"] for item in allowed_records),
            "denied_or_unscoped_files": denied_count,
            "denied_or_unscoped_bytes": denied_bytes,
            "pruned_paths": pruned,
        },
        "allowed_sources": allowed_records,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def tree_content_digest(root: str | Path) -> str:
    resolved = Path(root).resolve(strict=True)
    digest = hashlib.sha256()
    for directory, dirnames, filenames in os.walk(resolved, topdown=True, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        directory_path = Path(directory)
        for name in sorted(filenames):
            path = directory_path / name
            try:
                relative = path.relative_to(resolved).as_posix()
            except OSError:
                continue
            digest.update(f"{relative}\0".encode("utf-8"))
            if path.is_symlink():
                digest.update(f"symlink:{os.readlink(path)}\n".encode("utf-8"))
                continue
            try:
                with path.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
            except OSError:
                digest.update(b"[unreadable]")
            digest.update(b"\n")
    return digest.hexdigest()


def render_run_record(
    *,
    run: AgentRun,
    harness: NavigationHarness,
    manifest: dict[str, Any],
    pre_tree_digest: str,
    post_tree_digest: str,
    score: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    steps = []
    for step in run.steps:
        action = {
            "kind": step.action.kind,
            "message": step.action.message,
            "final_output": step.action.final_output,
            "meta": dict(step.action.meta),
            "tool_call": asdict(step.action.tool_call)
            if step.action.tool_call is not None
            else None,
        }
        observation = None
        if step.observation is not None:
            observation = {
                "kind": step.observation.kind,
                "text": step.observation.text,
                "meta": dict(step.observation.meta),
                "tool_result": asdict(step.observation.tool_result)
                if step.observation.tool_result is not None
                else None,
            }
        trace = asdict(step.trace) if step.trace is not None else None
        steps.append(
            {"index": step.index, "action": action, "observation": observation, "trace": trace}
        )
    return {
        "schema_version": 1,
        "config": dict(config or {}),
        "manifest_sha256": manifest["manifest_sha256"],
        "read_only_verified": pre_tree_digest == post_tree_digest,
        "pre_tree_digest": pre_tree_digest,
        "post_tree_digest": post_tree_digest,
        "run": {
            "status": run.status,
            "stop_reason": run.stop_reason,
            "final_output": run.final_output,
            "elapsed_seconds": run.elapsed_seconds,
            "step_count": len(run.steps),
            "steps": steps,
            "meta": run.meta,
        },
        "planner_usage": asdict(harness.planner.usage),
        "tool_telemetry": harness.tools.telemetry.calls,
        "automatic_pruned_paths": harness.tools.telemetry.automatic_pruned_paths,
        "denied_content_bytes": harness.tools.telemetry.denied_content_bytes,
        "score": score,
    }
