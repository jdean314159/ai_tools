#!/usr/bin/env python3
"""Assert package README tiers match the root README package table."""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = [
    "llm_harness_core",
    "llm_engines",
    "engram",
    "rag_lib",
    "llm_inspector",
    "llm_inspector_ui",
    "agent_lib",
]
TIER_HEADER = re.compile(r"^##\s*Tier:\s*(.+?)\s*$", re.MULTILINE)
TABLE_ROW = re.compile(
    r"^\|\s*\[([A-Za-z0-9_]+)\]\([^)]*\)\s*\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)


def normalize_tier(value: str) -> str:
    first_token = value.strip().split()[0]
    return first_token.strip("*_`").lower()


def header_tier(package: str) -> str | None:
    readme = ROOT / package / "README.md"
    if not readme.exists():
        return None

    match = TIER_HEADER.search(readme.read_text(encoding="utf-8"))
    return normalize_tier(match.group(1)) if match else None


def table_tiers() -> dict[str, str]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    return {
        match.group(1): normalize_tier(match.group(2))
        for match in TABLE_ROW.finditer(text)
    }


def main() -> int:
    table = table_tiers()
    failures: list[str] = []

    for package in PACKAGES:
        header = header_tier(package)
        table_value = table.get(package)
        if header is None:
            failures.append(f"{package}: no '## Tier:' header found")
        elif table_value is None:
            failures.append(f"{package}: not found in root README Packages table")
        elif header != table_value:
            failures.append(
                f"{package}: README header tier {header!r} "
                f"!= root table tier {table_value!r}"
            )

    if failures:
        print("Tier-label check FAILED:\n")
        print("\n".join(failures))
        return 1

    print("Tier-label check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
