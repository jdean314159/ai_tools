from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import threading
import time
from typing import Any

from agent_lib import AgentRun, AgentTask
from agent_lib.eval.repo_navigation import (
    LlamaServerClient,
    NavigationBudget,
    NavigationConfigurationError,
    NavigationPolicy,
    build_environment_manifest,
    build_navigation_harness,
    load_ground_truth,
    render_run_record,
    score_navigation_run,
    tree_content_digest,
    validate_ground_truth_snapshot,
)


class ResourceSampler:
    def __init__(self, interval_seconds: float = 0.25) -> None:
        self.interval_seconds = interval_seconds
        self.peak_gpu_memory_mib: int | None = None
        self.peak_system_used_memory_kib: int | None = None
        self.peak_model_server_rss_kib: int | None = None
        self._has_nvidia_smi = shutil.which("nvidia-smi") is not None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _system_used_memory_kib(self) -> int | None:
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0])
            return values["MemTotal"] - values["MemAvailable"]
        except (OSError, KeyError, ValueError):
            return None

    def _model_server_rss_kib(self) -> int | None:
        total = 0
        found = False
        for process_dir in Path("/proc").glob("[0-9]*"):
            try:
                command = (process_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
                if "llama-server" not in command and "llama_server" not in command:
                    continue
                status = (process_dir / "status").read_text(encoding="utf-8")
                match = next((line for line in status.splitlines() if line.startswith("VmRSS:")), None)
                if match:
                    total += int(match.split()[1])
                    found = True
            except (OSError, ValueError):
                continue
        return total if found else None

    def _sample_resources(self) -> None:
        while not self._stop.is_set():
            system_used = self._system_used_memory_kib()
            if system_used is not None:
                self.peak_system_used_memory_kib = max(self.peak_system_used_memory_kib or 0, system_used)
            server_rss = self._model_server_rss_kib()
            if server_rss is not None:
                self.peak_model_server_rss_kib = max(self.peak_model_server_rss_kib or 0, server_rss)
            if self._has_nvidia_smi:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
                    if values:
                        current = sum(values)
                        self.peak_gpu_memory_mib = max(self.peak_gpu_memory_mib or 0, current)
            self._stop.wait(self.interval_seconds)

    def __enter__(self) -> "ResourceSampler":
        self._thread = threading.Thread(target=self._sample_resources, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def metrics(self) -> dict[str, Any]:
        # Linux reports KiB; macOS reports bytes. This harness is currently exercised on Linux.
        return {
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "system_peak_used_memory_kib": self.peak_system_used_memory_kib,
            "model_server_peak_rss_kib": self.peak_model_server_rss_kib,
            "system_peak_gpu_memory_mib": self.peak_gpu_memory_mib,
        }


def _deployment_record(client: LlamaServerClient, expected_context_window: int) -> dict[str, Any]:
    deployment = client.deployment_info()
    settings = deployment.get("default_generation_settings")
    server_context = settings.get("n_ctx") if isinstance(settings, dict) else None
    if server_context is None or int(server_context) < expected_context_window:
        raise NavigationConfigurationError(
            f"llama-server context is too small: evaluation limit={expected_context_window}, server={server_context}"
        )
    template = str(deployment.get("chat_template") or "")
    if not template:
        raise NavigationConfigurationError("llama-server did not report its chat template")
    deployment["chat_template_sha256"] = hashlib.sha256(template.encode("utf-8")).hexdigest()
    deployment["evaluation_context_limit"] = expected_context_window
    deployment["cache_prompt"] = {"requested": False, "enforced_by": "native /completion request", "verified_per_response": True}
    return deployment


def _outside_root(path: Path, root: Path, label: str, *, must_exist: bool = True) -> Path:
    if must_exist or path.exists():
        resolved = path.resolve(strict=True)
    else:
        resolved = path.parent.resolve(strict=True) / path.name
    try:
        resolved.relative_to(root)
    except ValueError:
        return resolved
    raise NavigationConfigurationError(f"{label} must be outside the confined ai_tools root")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NAV-TEST-00 Qwen repository-navigation evaluation.")
    parser.add_argument("--root", type=Path, required=True, help="Confined ai_tools repository root")
    parser.add_argument("--answer-key", type=Path, required=True, help="Ground-truth JSON outside the confined root")
    parser.add_argument("--output-dir", type=Path, required=True, help="New or empty result directory outside the confined root")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="llama-server native API root")
    parser.add_argument("--model-label", default="qwen3.6:27b", help="Human label recorded with the pinned server deployment")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--min-p", type=float, default=0.0)
    parser.add_argument("--presence-penalty", type=float, default=1.5)
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--token-limit", type=int, default=120_000)
    parser.add_argument("--context-window", type=int, default=40_000)
    parser.add_argument("--minimum-output-reserve", type=int, default=512)
    parser.add_argument("--per-call-output-cap", type=int, default=2_048)
    parser.add_argument(
        "--action-guard-mode",
        choices=("off", "shadow", "enforce"),
        default="shadow",
        help="Disable, observe, or enforce the action-trajectory loop guard",
    )
    parser.add_argument(
        "--structured-navigation",
        action="store_true",
        help="Enable the experimental NAV-STRUCT-00 required-goal ledger",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve(strict=True)
    if "qwen3.6" not in args.model_label.lower():
        raise NavigationConfigurationError("NAV-TEST-00 is restricted to a pinned Qwen3.6 deployment")
    answer_key = _outside_root(args.answer_key, root, "answer key")
    output_dir = _outside_root(args.output_dir, root, "output directory", must_exist=False)
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise NavigationConfigurationError(f"Evaluation output directory must be new or empty: {output_dir}")
    question, regions = load_ground_truth(answer_key)
    budget = NavigationBudget(
        cumulative_token_limit=args.token_limit,
        context_window=args.context_window,
        minimum_output_reserve=args.minimum_output_reserve,
        per_call_output_cap=args.per_call_output_cap,
    )
    policy = NavigationPolicy(root)
    manifest = build_environment_manifest(policy)
    validate_ground_truth_snapshot(answer_key, manifest, root)
    client = LlamaServerClient(
        args.base_url,
        seed=args.seed,
        top_k=args.top_k,
        top_p=args.top_p,
        min_p=args.min_p,
        presence_penalty=args.presence_penalty,
    )
    deployment = _deployment_record(client, args.context_window)
    deployment["model_label"] = args.model_label
    config = {
        "deployment": deployment,
        "decoding": {
            "temperature": args.temperature,
            "seed": args.seed,
            "top_k": args.top_k,
            "top_p": args.top_p,
            "min_p": args.min_p,
            "presence_penalty": args.presence_penalty,
            "sampling_parameters_applied": args.temperature > 0,
            "cache_prompt_requested": False,
            "cache_prompt_enforced": True,
            "cache_prompt_verified_per_response": True,
            "thinking_disabled": True,
        },
        "budget": {
            "max_steps": args.max_steps,
            "cumulative_token_limit": args.token_limit,
            "context_window": args.context_window,
            "minimum_output_reserve": args.minimum_output_reserve,
            "per_call_output_cap": args.per_call_output_cap,
        },
        "answer_key_sha256": hashlib.sha256(answer_key.read_bytes()).hexdigest(),
        "action_guard_mode": args.action_guard_mode,
        "structured_navigation": args.structured_navigation,
    }
    harness = build_navigation_harness(
        root=root,
        engine=client,
        tokenizer=client,
        policy=policy,
        budget=budget,
        max_steps=args.max_steps,
        temperature=args.temperature,
        metadata={"eval": "NAV-TEST-00", "seed": args.seed, "backend": "llama-server"},
        action_guard_mode=args.action_guard_mode,
        structured_navigation=args.structured_navigation,
    )
    pre_digest = tree_content_digest(root)
    started = time.perf_counter()
    with ResourceSampler() as resources:
        try:
            run = harness.run(question)
        except Exception as exc:
            run = AgentRun(
                task=AgentTask(task_id="nav-test-00", goal=question),
                status="error",
                stop_reason="error",
                final_output=f"Navigation run failed: {type(exc).__name__}: {exc}",
                meta={"error_type": type(exc).__name__, "error": str(exc)},
            )
    wall_time = time.perf_counter() - started
    post_digest = tree_content_digest(root)
    score = score_navigation_run(
        run,
        harness.tools.telemetry,
        regions,
        budget,
        max_steps=args.max_steps,
        source_root=root,
    )
    score["read_only_verified"] = pre_digest == post_digest
    score["passed"] = bool(score["passed"] and score["read_only_verified"])
    score["wall_time_seconds"] = wall_time
    score.update(resources.metrics())
    if run.status == "error":
        score["run_error"] = run.meta.get("error")
    record = render_run_record(
        run=run,
        harness=harness,
        manifest=manifest,
        pre_tree_digest=pre_digest,
        post_tree_digest=post_digest,
        score=score,
        config=config,
    )
    output_dir.mkdir(parents=False, exist_ok=True)
    (output_dir / "environment-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "run-record.json").write_text(json.dumps(record, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(score, indent=2, sort_keys=True))
    return 0 if score["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
