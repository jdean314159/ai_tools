#!/usr/bin/env python3
"""Validate that relative Markdown links resolve to real files."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vendored import is_vendored


LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FENCED_CODE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
ROOT = Path(__file__).resolve().parents[1]


def tracked_markdown() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / path for path in result.stdout.splitlines() if path]


def is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def main() -> int:
    markdown_files = tracked_markdown()
    failures: list[str] = []

    for markdown_file in markdown_files:
        relative_file = markdown_file.relative_to(ROOT)
        if is_vendored(relative_file.as_posix()):
            continue

        text = FENCED_CODE.sub("", markdown_file.read_text(encoding="utf-8"))
        for match in LINK.finditer(text):
            target = match.group(1).strip()
            if is_external(target):
                continue

            path_part = target.split("#", 1)[0]
            if not path_part:
                continue

            resolved = (markdown_file.parent / path_part).resolve()
            if not resolved.exists():
                failures.append(f"{relative_file}: broken link -> {target}")

    if failures:
        print("Markdown link check FAILED:\n")
        print("\n".join(failures))
        return 1

    print(f"Markdown link check passed ({len(markdown_files)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
