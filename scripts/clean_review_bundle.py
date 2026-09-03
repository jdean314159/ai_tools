#!/usr/bin/env python3
"""Remove local-only artifacts from an explicit disposable review checkout."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".bak"}


def _validated_target(raw_target: str) -> Path:
    target = Path(raw_target).expanduser().resolve(strict=True)
    repo = REPO_ROOT.resolve(strict=True)
    if target == repo or target in repo.parents or repo in target.parents:
        raise ValueError(
            "review cleanup target must not be this checkout, one of its parents, "
            "or a path inside it"
        )
    if target == Path(target.anchor) or target == Path.home().resolve():
        raise ValueError("review cleanup target must not be a filesystem root or home directory")
    if not (target / "pyproject.toml").is_file():
        raise ValueError("review cleanup target must contain the ai_tools root pyproject.toml")
    return target


def clean_review_bundle(target: Path) -> None:
    for path in sorted(target.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and (path.name in CACHE_DIR_NAMES or path.name.endswith(".egg-info")):
            shutil.rmtree(path)
        elif path.is_file() and (
            path.suffix in DATABASE_SUFFIXES
            or path.name.endswith((".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm"))
        ):
            path.unlink()
    for relative in (".git", "models", "engram/data/memory", "llm_inspector_ui/data"):
        path = target / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Explicit disposable ai_tools review checkout")
    args = parser.parse_args()
    try:
        target = _validated_target(args.target)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    clean_review_bundle(target)
    print(f"Review bundle workspace cleaned: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
