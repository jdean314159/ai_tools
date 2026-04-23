from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_monorepo_root_import_smoke() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import llm_inspector; "
            "assert hasattr(llm_inspector, 'describe_inspector'); "
            "assert hasattr(llm_inspector, 'trace_to_operation_result'); "
            "print('ok')",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "ok"
