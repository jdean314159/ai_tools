"""Corrected external grader for the valid defects at commit 23c1549.

The frozen three-test grader incorrectly treated absence of a later-added Spark
configuration entry as a defect. This post-run correction retains only the two
behaviors that existed on the target and were fixed afterward.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from agent_lib.interop import _tool_execution_state


def _repo_root() -> Path:
    value = os.environ.get("ASSESSMENT_REPO_ROOT", "")
    if not value:
        raise RuntimeError("ASSESSMENT_REPO_ROOT is required")
    root = Path(value).resolve()
    if not (root / "AGENTS.md").is_file():
        raise RuntimeError(f"ASSESSMENT_REPO_ROOT is not an ai_tools export: {root}")
    return root


def test_ungranted_tool_is_classified_as_policy_block() -> None:
    state = _tool_execution_state({"error": "tool_not_granted"})

    assert state == {"error": "tool_not_granted", "blocked": True}


def test_publication_hygiene_fails_closed_without_git_metadata() -> None:
    root = _repo_root()
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_publication_hygiene.py"), "--tracked-only"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Tracked-file inventory is unavailable:" in result.stdout
