from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_bundle_writes_json(tmp_path: Path):
    out_json = tmp_path / "bundle.json"
    cmd = [
        sys.executable,
        "-m",
        "llm_inspector.cli",
        "bundle",
        "hello world",
        "--adapters",
        "baseline,baseline",
        "--json-out",
        str(out_json),
        "--no-print",
    ]
    subprocess.check_call(cmd)

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert "report" in payload
    assert "diffs" in payload
    assert payload["report"]["query"] == "hello world"
    # baseline + baseline => 2 traces, 1 pairwise diff
    assert len(payload["report"]["traces"]) == 2
    assert len(payload["diffs"]) == 1