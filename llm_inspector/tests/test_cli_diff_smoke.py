from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


def _engram_runtime_available() -> bool:
    if importlib.util.find_spec("engram") is None:
        return False
    try:
        from engram.project_memory import ProjectMemory  # noqa: F401
    except Exception:
        return False
    return True


def test_cli_diff_baseline_baseline_smoke():
    # Always available; does not require Engram.
    cmd = [
        sys.executable,
        "-m",
        "llm_inspector.cli",
        "diff",
        "hello world",
        "--adapter-a",
        "baseline",
        "--adapter-b",
        "baseline",
        "--no-print",
    ]
    subprocess.check_call(cmd)


@pytest.mark.engram
def test_cli_diff_baseline_engram_smoke(tmp_path: Path):
    # Only run if Engram is importable.
    if not _engram_runtime_available():
        pytest.skip("engram not importable with its runtime dependencies")

    cmd = [
        sys.executable,
        "-m",
        "llm_inspector.cli",
        "diff",
        "hello world",
        "--adapter-a",
        "baseline",
        "--adapter-b",
        "engram",
        "--engram-base-dir",
        str(tmp_path),
        "--no-print",
    ]
    subprocess.check_call(cmd)