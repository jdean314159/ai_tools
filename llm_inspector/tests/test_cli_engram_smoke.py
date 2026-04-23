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


@pytest.mark.engram
def test_cli_engram_smoke(tmp_path: Path):
    if not _engram_runtime_available():
        pytest.skip("engram not importable with its runtime dependencies")

    cmd = [
        sys.executable,
        "-m",
        "llm_inspector.cli",
        "compare",
        "hello world",
        "--adapter",
        "engram",
        "--engram-base-dir",
        str(tmp_path),
        "--no-print",
    ]
    subprocess.check_call(cmd)
