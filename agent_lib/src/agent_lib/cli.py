from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .examples.programming_evaluation import run_programming_benchmark, run_programming_scenario_benchmark
from .examples.programming_task import run_programming_demo_from_file, write_programming_config_file
from .programming import load_programming_runtime_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-lib", description="Utilities for agent_lib programming workflows.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cfg = sub.add_parser("init-programming-config", help="Write a starter programming config JSON file.")
    init_cfg.add_argument("--output", required=True, help="Path to the JSON config file to write.")
    init_cfg.add_argument("--session-id", default="programming_demo")
    init_cfg.add_argument("--path", dest="task_path", default="main.py", help="Target source path for the demo task.")
    init_cfg.add_argument("--memory-backend", default="engram_lite", choices=["engram_lite", "engram"])
    init_cfg.add_argument("--mentor", default=None, help="Named mentor/planner engine in llm_engines config.")
    init_cfg.add_argument("--worker", default=None, help="Named worker/executor engine in llm_engines config.")
    init_cfg.add_argument("--critic", default=None, help="Named critic engine in llm_engines config.")

    run_cfg = sub.add_parser("run-programming", help="Run the programming demo from a JSON/TOML config file.")
    run_cfg.add_argument("--config", required=True, help="Path to the programming runtime config (.json or .toml).")
    run_cfg.add_argument("--root", default=None, help="Workspace root for the run. Defaults to a temporary directory.")
    run_cfg.add_argument("--engines-config", default=None, help="Path to llm_engines.yaml for loading named mentor/worker/critic engines.")
    run_cfg.add_argument("--max-steps", type=int, default=12)
    run_cfg.add_argument("--print-config", action="store_true", help="Print the resolved programming config before running.")

    eval_cmp = sub.add_parser("evaluate-programming-scenarios", help="Run comparative benchmark scenarios across memory backends/runtime profiles.")
    eval_cmp.add_argument("--root", default=None, help="Root directory under which per-scenario workspaces will be created.")
    eval_cmp.add_argument("--output", default=None, help="Optional path to save the JSON report.")

    eval_cmd = sub.add_parser("evaluate-programming", help="Run the representative programming benchmark suite.")
    eval_cmd.add_argument("--root", default=None, help="Root directory under which per-case workspaces will be created.")
    eval_cmd.add_argument("--output", default=None, help="Optional path to save the JSON report.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-programming-config":
        path = write_programming_config_file(
            args.output,
            session_id=args.session_id,
            task_path=args.task_path,
            memory_backend=args.memory_backend,
            mentor=args.mentor,
            worker=args.worker,
            critic=args.critic,
        )
        print(path)
        return 0

    if args.command == "run-programming":
        config = load_programming_runtime_config(args.config)
        if args.print_config:
            print(json.dumps(config.to_dict(), indent=2, sort_keys=True))
        run, root = run_programming_demo_from_file(
            args.config,
            root=args.root,
            engine_config_path=args.engines_config,
            max_steps=args.max_steps,
        )
        payload = {
            "status": run.status,
            "stop_reason": run.stop_reason,
            "final_output": run.final_output,
            "workspace_root": str(Path(root)),
            "steps": len(run.steps),
            "escalations": run.escalations,
            "elapsed_seconds": getattr(run, "elapsed_seconds", None),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "evaluate-programming-scenarios":
        report = run_programming_scenario_benchmark(root=args.root)
        payload = report.to_dict()
        if args.output:
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "evaluate-programming":
        report = run_programming_benchmark(root=args.root)
        payload = report.to_dict()
        if args.output:
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if report.failed == 0 else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
