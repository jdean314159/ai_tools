#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _prepend_repo_pythonpath(env: dict[str, str], repo_root: Path) -> None:
    candidates = [
        repo_root,
        repo_root / "llm_harness_core" / "src",
        repo_root / "engram_lite" / "src",
        repo_root / "engram" / "src",
        repo_root / "llm_engines" / "src",
        repo_root / "llm_inspector" / "src",
        repo_root / "rag_lib" / "src",
        repo_root / "agent_lib" / "src",
        repo_root / "language_tutor" / "src",
        repo_root / "llm_inspector_ui",
    ]
    existing = env.get("PYTHONPATH", "")
    parts = [str(path) for path in candidates if path.exists()]
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the ai_tools memory evaluation harness with real-model answer evaluation."
    )
    parser.add_argument("--repo-root", default=".", help="Path to the ai_tools repo root.")
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible server base URL, e.g. http://localhost:8080")
    parser.add_argument("--model", required=True, help="Model name exposed by the server.")
    parser.add_argument("--api-key", default="", help="Optional API key for the server.")
    parser.add_argument("--json-out", default="memory_eval_answer_report.json", help="Output JSON report path.")
    parser.add_argument("--markdown-out", default="memory_eval_answer_report.md", help="Output Markdown report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    harness = repo_root / "integration_tests" / "memory_eval.py"
    if not harness.exists():
        print(f"Could not find harness at {harness}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    _prepend_repo_pythonpath(env, repo_root)

    env["MEMORY_EVAL_OPENAI_BASE_URL"] = args.base_url.rstrip("/")
    env["MEMORY_EVAL_MODEL"] = args.model
    if args.api_key:
        env["MEMORY_EVAL_OPENAI_API_KEY"] = args.api_key
        
    cmd = [
        sys.executable,
        str(harness),
        "--suite",
        "--with-model",
        "--json",
        str(Path(args.json_out).resolve()),
        "--markdown",
        str(Path(args.markdown_out).resolve()),
    ]

    print("Running:")
    print(" ".join(cmd))
    print(f"Base URL: {env['MEMORY_EVAL_OPENAI_BASE_URL']}")
    print(f"Model: {env['MEMORY_EVAL_MODEL']}")
    result = subprocess.run(cmd, cwd=str(repo_root), env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
