from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_diff_writes_json(tmp_path: Path):
    out_json = tmp_path / "diff.json"
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
        "--json-out",
        str(out_json),
        "--no-print",
    ]
    subprocess.check_call(cmd)

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["name_a"] == "baseline"
    assert payload["name_b"] == "baseline"
    assert "section_deltas" in payload
    assert "flags" in payload