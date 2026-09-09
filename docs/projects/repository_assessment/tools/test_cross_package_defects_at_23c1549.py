"""External grader for the cross-package target at commit 23c1549.

These regressions cover fixes committed after the target in ``agent_lib``,
``llm_engines``, and the publication-hygiene script. They are expected to fail
3/3 on the target and pass 3/3 on corrected reference commit 49026ea or a
descendant. Set ``ASSESSMENT_REPO_ROOT`` to the exported repository root.
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


def test_shipped_engine_config_contains_no_private_deployment_address() -> None:
    config = _repo_root() / "llm_engines" / "src" / "llm_engines" / "data" / "llm_engines.yaml"
    content = config.read_text(encoding="utf-8")

    assert "192.168.50.225" not in content
    assert "http://inference-host:8080/v1" in content


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
