from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_compare_writes_json(tmp_path: Path):
    out_json = tmp_path / "report.json"
    cmd = [
        sys.executable,
        "-m",
        "llm_inspector.cli",
        "compare",
        "hello world",
        "--json-out",
        str(out_json),
        "--no-print",
    ]
    subprocess.check_call(cmd)
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["query"] == "hello world"
    assert payload["traces"][0]["name"] == "baseline"
