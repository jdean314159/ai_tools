"""Build the frozen source-span manifest for the Ornith A/B/C test."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc/span-manifest.json"

ITEMS = [
    ("23c1549d5aae3ac67454aade1b725f2931770014", "agent_lib/src/agent_lib/interop.py", 22, 58, "defect_tool_state"),
    ("23c1549d5aae3ac67454aade1b725f2931770014", "llm_engines/src/llm_engines/data/llm_engines.yaml", 75, 86, "defect_private_address"),
    ("23c1549d5aae3ac67454aade1b725f2931770014", "scripts/check_publication_hygiene.py", 17, 35, "defect_git_fail_open"),
    ("7d37920a81a9cb672c24af3a55557621e5c5009f", "engram/src/engram/project_memory.py", 318, 327, "defect_path_escape"),
    ("7d37920a81a9cb672c24af3a55557621e5c5009f", "engram/src/engram/project_memory.py", 1990, 2025, "defect_cross_tenant_delete"),
]

def show(commit: str, path: str) -> list[str]:
    data = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT, text=True)
    return data.splitlines()

def main() -> None:
    rows = []
    for commit, path, start, end, label in ITEMS:
        lines = show(commit, path)
        text = "\n".join(lines[start - 1 : end]) + "\n"
        rows.append({"item_id": label, "kind": "defect", "commit": commit, "path": path, "start_line": start, "end_line": end, "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text})
    payload = {"schema": "oracle-localization-span-manifest/v1", "items": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
