from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from agent_lib import CoordinationMessage, ExternalAgentSession, ExternalSessionCoordinator

from .exchange import ExchangeRecorder
from .monitor import LiveConsoleMonitor
from .planner import Planner
from .workers import WorkerSpec, build_worker, detect_worker_capabilities


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspectable external-agent coordination teaching demo")
    parser.add_argument("--task", default="Create a tiny README note for the teaching workspace.")
    parser.add_argument("--workers", default="mock", help="comma-separated: mock,codex,claude_code")
    parser.add_argument("--planner-backend", default="mock")
    parser.add_argument("--planner-model", default="mock-planner")
    parser.add_argument("--worker-backend", default="ollama", help="backend for llm_engine workers")
    parser.add_argument("--worker-model", default=None, help="model tag or GGUF path for llm_engine workers")
    parser.add_argument("--worker-base-url", default=None, help="OpenAI-compatible endpoint for llm_engine workers")
    parser.add_argument("--worker-local", action="store_true", help="mark OpenAI-compatible llm_engine worker as local")
    parser.add_argument("--worker-n-gpu-layers", type=int, default=None, help="llama.cpp GPU-offloaded layer count")
    parser.add_argument("--worker-n-ctx", type=int, default=None, help="llama.cpp context window")
    parser.add_argument("--worker-n-threads", type=int, default=None, help="llama.cpp CPU thread count")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--monitor", action="store_true", help="open a simple monitor command loop after the run")
    args = parser.parse_args()

    worker_kinds = [item.strip() for item in args.workers.split(",") if item.strip()]
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    workspace = Path(args.workspace) if args.workspace else Path(tempfile.mkdtemp(prefix="agent_coord_workspace_"))
    run_dir = Path(args.run_dir) if args.run_dir else Path("examples/agent_coordination_teaching/runs") / run_id
    workspace.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Agent Coordination Teaching Workspace\n", encoding="utf-8")

    recorder = ExchangeRecorder(run_dir, run_id=run_id, thread_id=run_id)
    coordinator = ExternalSessionCoordinator()
    coordinator.mailbox.register(ExternalAgentSession(agent_id="planner", role="planner", workspace=str(workspace)))

    capabilities = detect_worker_capabilities()
    recorder.record(
        "capability_discovery",
        actor="demo",
        summary="Detected available worker launch capabilities.",
        body=json.dumps(capabilities, indent=2, sort_keys=True),
        metadata=capabilities,
    )

    worker_specs = [_build_worker_spec(kind, args) for kind in worker_kinds]
    monitor = LiveConsoleMonitor(
        recorder,
        coordinator=coordinator,
        recipients=[spec.name for spec in worker_specs],
    )
    for spec in worker_specs:
        coordinator.mailbox.register(ExternalAgentSession(agent_id=spec.name, role=spec.kind, workspace=str(workspace)))

    planner = Planner(backend=args.planner_backend, model=args.planner_model)
    assignments = planner.plan(task=args.task, workers=[spec.name for spec in worker_specs])
    recorder.record(
        "planner_selected",
        actor="demo",
        summary=f"Planner backend: {args.planner_backend}/{args.planner_model}",
    )

    for assignment in assignments:
        body = (
            f"# {assignment.title}\n\n"
            f"{assignment.instructions}\n\n"
            "Coordination rules:\n"
            "- Work only inside the provided workspace.\n"
            "- Treat file reservations as advisory ownership signals.\n"
            "- Keep output concise and explain what happened.\n"
            "- Do not run destructive commands.\n"
        )
        message = coordinator.send(
            "planner",
            assignment.worker,
            kind="handoff",
            subject=assignment.title,
            body=body,
            thread_id=run_id,
            metadata={"files": list(assignment.files)},
        )
        _record_message(recorder, message, event_type="assignment_sent")
        reservations = coordinator.reserve_paths(
            assignment.worker,
            assignment.files,
            thread_id=run_id,
            note=assignment.title,
        )
        for reservation in reservations:
            recorder.record(
                f"reservation_{reservation.status}",
                actor=assignment.worker,
                summary=f"{reservation.status}: {reservation.path}",
                related_files=[reservation.path],
                metadata=asdict(reservation),
            )

    manifest = {
        "run_id": run_id,
        "task": args.task,
        "planner": {"backend": args.planner_backend, "model": args.planner_model},
        "workers": [asdict(spec) for spec in worker_specs],
        "workspace": str(workspace),
        "run_dir": str(run_dir),
        "dry_run": args.dry_run,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    if args.dry_run:
        monitor.print_recent(limit=20)
        print(f"\nDry run complete. Artifacts: {run_dir}")
        return

    if args.monitor:
        monitor.print_recent(limit=30)
        monitor.command_loop(phase="pre-launch")

    for spec in worker_specs:
        adapter = build_worker(spec)
        if not adapter.available():
            recorder.record(
                "worker_unavailable_warning",
                actor=spec.name,
                summary=f"{spec.kind} launcher is not available on PATH.",
            )
            continue
        inbox = coordinator.inbox(spec.name, thread_id=run_id)
        prompt = "\n\n".join(message.body for message in inbox)
        recorder.record("worker_launch_started", actor=spec.name, summary=f"Launching {spec.kind} worker.")
        result = adapter.launch(workspace=workspace, prompt=prompt, timeout_seconds=args.timeout_seconds)
        recorder.record(
            "worker_completed" if result.success else "worker_failed_warning",
            actor=spec.name,
            summary=f"{spec.name} exited with code {result.returncode}.",
            body=result.output,
            metadata={"command": list(result.command), "returncode": result.returncode},
        )

    monitor.print_recent(limit=30)
    print(f"\nArtifacts: {run_dir}")
    if args.monitor:
        monitor.command_loop(phase="post-run")


def _record_message(recorder: ExchangeRecorder, message: CoordinationMessage, *, event_type: str) -> None:
    recorder.record(
        event_type,
        actor=message.sender,
        target=message.recipient,
        summary=message.subject,
        body=message.body,
        related_files=tuple(message.metadata.get("files") or ()),
        metadata={
            "message_id": message.message_id,
            "kind": message.kind,
            "created_at": message.created_at.isoformat(),
        },
    )


def _build_worker_spec(kind: str, args: argparse.Namespace) -> WorkerSpec:
    if kind == "llm_engine":
        return WorkerSpec(
            name="llm_engine_worker",
            kind=kind,
            backend=args.worker_backend,
            model=args.worker_model,
            base_url=args.worker_base_url,
            is_cloud=False if args.worker_local else None,
            n_gpu_layers=args.worker_n_gpu_layers,
            n_ctx=args.worker_n_ctx,
            n_threads=args.worker_n_threads,
        )
    return WorkerSpec(name=f"{kind}_worker", kind=kind)


if __name__ == "__main__":
    main()
