#!/usr/bin/env python3
"""Library packages must not link into teaching or course material."""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PACKAGES = (
    "llm_harness_core",
    "llm_engines",
    "engram",
    "rag_lib",
    "llm_inspector",
    "llm_inspector_ui",
    "agent_lib",
)
FORBIDDEN_TARGETS = (
    "docs/learning",
    "course/",
    "LEARNING_PATH.md",
    "CURRICULUM.md",
)
LINK = re.compile(r"\]\(([^)]+)\)")
FENCED_CODE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)


def main() -> int:
    failures: list[str] = []
    for package in LIBRARY_PACKAGES:
        for markdown_file in (ROOT / package).rglob("*.md"):
            text = FENCED_CODE.sub("", markdown_file.read_text(encoding="utf-8"))
            for match in LINK.finditer(text):
                target = match.group(1).strip()
                if any(forbidden in target for forbidden in FORBIDDEN_TARGETS):
                    relative_file = markdown_file.relative_to(ROOT)
                    failures.append(
                        f"{relative_file}: links into course material -> {target}"
                    )

    if failures:
        print("Dependency-direction check FAILED:\n" + "\n".join(failures))
        return 1

    print("Dependency-direction check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
