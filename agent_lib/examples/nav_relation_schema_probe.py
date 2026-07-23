from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_lib.eval.relation_schema_probe import run_relation_schema_probe
from agent_lib.eval.repo_navigation import LlamaServerClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the formatter-only NAV-VERIFIABLE-00 relation-schema probe."
    )
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--task-set", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1_024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = LlamaServerClient(args.base_url, seed=args.seed)
    result = run_relation_schema_probe(
        engine=client,
        fixture_root=args.fixture_root,
        task_set_path=args.task_set,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
