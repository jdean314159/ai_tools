#!/usr/bin/env python3
"""Validate publication hygiene for the ai_tools monorepo."""
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

def _git_tracked_files() -> set[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()}


def _git_tracked_dirs() -> set[Path]:
    """Directories that contain at least one git-tracked file."""
    dirs: set[Path] = set()
    for f in _git_tracked_files():
        for parent in f.parents:
            if parent == ROOT:
                break
            dirs.add(parent)
    return dirs

REQUIRED_ROOT_DOCS = [
    "README.md",
    "ADR_INDEX.md",
    "LICENSE",
    "CONTRIBUTING.md",
]

LEGACY_BASENAMES = {
    "README_engram_lite.legacy.md",
    "README_llm_inspector.legacy.md",
    "README_llm_inspector_ui.legacy.md",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
}

BANNED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    "test_reports",
    "test_survey_results",
    "local_artifacts",
}


BANNED_DIR_SUFFIXES = {
    ".egg-info",
}

BANNED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".bak",
    ".orig",
    ".rej",
    ".patch",
}


def _is_under_skipped_dir(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.relative_to(ROOT).parts)


def _preview(paths: list[Path], limit: int = 10) -> str:
    rendered = ", ".join(str(path) for path in paths[:limit])
    if len(paths) > limit:
        rendered += f" ... (+{len(paths) - limit} more)"
    return rendered


def _find_banned_dirs() -> dict[str, list[Path]]:
    findings: dict[str, list[Path]] = {}

    for path in _git_tracked_dirs():
        if _is_under_skipped_dir(path):
            continue

        rel = path.relative_to(ROOT)
        reason: str | None = None

        if path.name in BANNED_DIR_NAMES:
            reason = path.name
        else:
            for suffix in BANNED_DIR_SUFFIXES:
                if path.name.endswith(suffix):
                    reason = f"*{suffix}"
                    break

        if reason:
            findings.setdefault(reason, []).append(rel)

    return findings


def _find_banned_files() -> dict[str, list[Path]]:
    findings: dict[str, list[Path]] = {}

    for path in _git_tracked_dirs():
        for path in _git_tracked_files():
            if _is_under_skipped_dir(path):
                continue

        rel = path.relative_to(ROOT)

        for suffix in BANNED_FILE_SUFFIXES:
            if path.name.endswith(suffix):
                findings.setdefault(f"*{suffix}", []).append(rel)
                break

    return findings


def main() -> int:
    problems: list[str] = []

    for rel in REQUIRED_ROOT_DOCS:
        if not (ROOT / rel).exists():
            problems.append(f"missing required root document: {rel}")

    for reason, paths in sorted(_find_banned_dirs().items()):
        problems.append(f"found banned directory pattern {reason}: {_preview(sorted(paths))}")

    for reason, paths in sorted(_find_banned_files().items()):
        problems.append(f"found banned file pattern {reason}: {_preview(sorted(paths))}")

    misplaced_legacy = []
    for path in ROOT.rglob("*.md"):
        if _is_under_skipped_dir(path):
            continue
        if path.name in LEGACY_BASENAMES and "docs/history" not in str(path.parent):
            misplaced_legacy.append(path.relative_to(ROOT))

    if misplaced_legacy:
        problems.append(
            "legacy package READMEs should live under docs/history/: "
            + ", ".join(str(p) for p in sorted(misplaced_legacy))
        )

    if problems:
        print("Publication hygiene check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("Publication hygiene check passed.")
    print("Required root docs present:", ", ".join(REQUIRED_ROOT_DOCS))
    print("No banned transient artifacts found.")
    print("Legacy package READMEs are confined to docs/history/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
