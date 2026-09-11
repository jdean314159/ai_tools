"""Create the pre-generation freeze manifest for the Ornith localization test."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


FROZEN_PATHS = (
    "docs/projects/repository_assessment/ORNITH-ORACLE-LOCALIZATION-ABC-PREREGISTRATION-2026-09-10.md",
    "docs/projects/repository_assessment/ORNITH-ORACLE-LOCALIZATION-ABC-PREGENERATION-CORRECTION-2026-09-10.md",
    "docs/projects/repository_assessment/TARGET-ACQUISITION-2026-09-08.md",
    "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc/span-manifest.json",
    "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc/oracle-manifest.json",
    "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc/prompts.json",
    "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc/run-matrix.json",
    "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc/scorer-controls.json",
    "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc/preflight-validation.json",
    "docs/projects/repository_assessment/tools/build_oracle_localization_manifest.py",
    "docs/projects/repository_assessment/tools/capture_llamacpp_endpoint.py",
    "docs/projects/repository_assessment/tools/freeze_oracle_localization.py",
    "docs/projects/repository_assessment/tools/run_oracle_localization.py",
    "docs/projects/repository_assessment/tools/score_oracle_localization.py",
    "docs/projects/repository_assessment/tools/validate_oracle_localization.py",
    "docs/projects/repository_assessment/tools/test_cross_package_defects_at_23c1549_corrected.py",
    "docs/projects/repository_assessment/tools/test_engram_boundary_defects_at_7d37920.py",
    "tests/test_repository_assessment_oracle_localization.py",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"refusing to overwrite {output}")
    campaign_root = output.parent
    if any(campaign_root.glob("generations*")):
        parser.error("refusing to freeze after a generation set exists")
    digests = {}
    for relative in FROZEN_PATHS:
        path = repo_root / relative
        if not path.is_file():
            parser.error(f"missing frozen path: {relative}")
        digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {
        "schema": "oracle-localization-freeze-manifest/v1",
        "frozen_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generation_started": False,
        "git_head_before_freeze": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip(),
        "model": "Ornith-1.5-35B-Q4_K_M.gguf",
        "conditions": ["A-existing-unpaired-anchor", "B", "C"],
        "seeds": [17, 31, 47],
        "fresh_run_count": 60,
        "sha256": digests,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
