#!/usr/bin/env python3
"""Fail if archived or removed identifiers appear in tracked files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vendored import is_vendored


ROOT = Path(__file__).resolve().parents[1]

DENYLIST = [
    ("make install-ml", "install-ml target was removed (SPEC-HYGIENE-02)"),
    ("engram[ml-dev]", "engram has no ml-dev extra (ADR-009)"),
    ("engram[neural]", "engram has no neural extra; RTRL layer archived (ADR-009)"),
    ("engram_lite", "engram_lite was renamed to engram (ADR-009)"),
    ("llm_engines/llm_engines", "llm_engines is src/ layout since ADR-014"),
]

ALLOWLIST_PATHS = {
    "ADR_INDEX.md",
    "WAVE4-README.md",
    "SPEC-GATE-02-ghost-references.md",
    "adr/ADR-008-monorepo-packaging-policy.md",
    "scripts/check_ghost_references.py",
    "scripts/check_publication_hygiene.py",
    "agent_lib/src/agent_lib/memory.py",
    "adr/ADR-007-engram-lite-as-engram-facade.md",
    "adr/ADR-007-step2-audit.md",
    "adr/ADR-009-engram-freeze-and-rename.md",
    "adr/ADR-014-import-topology.md",
    "docs/projects/diagnostics_agent/SPEC_multi_backend_engine_v2.md",
    "docs/internal/ENGRAM_SOURCE_PROVENANCE_REVIEW.md",
    "docs/projects/RUN-RECORD-00-PHASE-8-COURSE-PORTABILITY.md",
}

# Path prefixes where denylisted identifiers are legitimate history, not drift.
ALLOWLIST_PATH_PREFIXES = (
    "docs/history/",
    "SPEC-",
)

SCANNED_NAMES = {"Makefile"}
SCANNED_SUFFIXES = {
    ".cfg",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [path for path in result.stdout.splitlines() if path]


def path_allowlisted(path: str) -> bool:
    return path in ALLOWLIST_PATHS or path.startswith(ALLOWLIST_PATH_PREFIXES)


def main() -> int:
    failures: list[str] = []
    for relative_path in tracked_files():
        if is_vendored(relative_path):
            continue

        if not path_allowlisted(relative_path):
            for pattern, reason in DENYLIST:
                if pattern in relative_path:
                    failures.append(f"{relative_path}: PATH contains {pattern!r} - {reason}")

        if path_allowlisted(relative_path):
            continue

        path = Path(relative_path)
        if path.name not in SCANNED_NAMES and path.suffix not in SCANNED_SUFFIXES:
            continue

        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue

        for pattern, reason in DENYLIST:
            if pattern in text:
                failures.append(f"{relative_path}: contains {pattern!r} - {reason}")

    if failures:
        print("Ghost-reference check FAILED:\n")
        print("\n".join(failures))
        return 1

    print("Ghost-reference check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
