#!/usr/bin/env python3
"""Validate publication hygiene for the ai_tools monorepo."""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
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

FIXTURE_DIR_NAME = "fixtures"
TEST_FILE_PREFIX = "test_"
TEST_FILE_SUFFIX = "_test.py"
FIXTURE_REFERENCE_SKIP_MARKER = "hygiene: ignore-fixture-references"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
}

BANNED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".language_tutor_example",
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


def _walk_working_tree() -> Iterator[Path]:
    """Yield files and directories under ROOT, pruning only explicitly skipped dirs."""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_NAMES]
        base = Path(dirpath)
        for dirname in dirnames:
            yield base / dirname
        for filename in filenames:
            yield base / filename


def _iter_test_files() -> Iterator[Path]:
    for path in _walk_working_tree():
        if not path.is_file() or path.suffix != ".py":
            continue
        if path.name.startswith(TEST_FILE_PREFIX) or path.name.endswith(TEST_FILE_SUFFIX):
            yield path


def _preview(paths: list[Path], limit: int = 10) -> str:
    rendered = ", ".join(str(path) for path in paths[:limit])
    if len(paths) > limit:
        rendered += f" ... (+{len(paths) - limit} more)"
    return rendered


def _banned_reason(path: Path) -> str | None:
    name = path.name

    if path.is_dir():
        if name in BANNED_DIR_NAMES:
            return name
        for suffix in BANNED_DIR_SUFFIXES:
            if name.endswith(suffix):
                return f"*{suffix}"
        return None

    for suffix in BANNED_FILE_SUFFIXES:
        if name.endswith(suffix):
            return f"*{suffix}"
    return None


def _is_under_reported_banned_dir(path: Path, banned_dirs: list[Path]) -> bool:
    return any(parent == path or parent in path.parents for parent in banned_dirs)


def _is_tracked_path(path: Path, tracked: set[Path]) -> bool:
    if path.is_dir():
        return any(tracked_file == path or path in tracked_file.parents for tracked_file in tracked)
    return path in tracked


def _classify_findings() -> dict[str, dict[str, list[Path]]]:
    """Return banned paths split by tracked publish gate and untracked workspace gate."""
    tracked = {path.resolve() for path in _git_tracked_files()}
    result: dict[str, dict[str, list[Path]]] = {"tracked": {}, "untracked": {}}
    reported_banned_dirs: list[Path] = []

    for path in _walk_working_tree():
        path = path.resolve()
        if _is_under_reported_banned_dir(path, reported_banned_dirs):
            continue

        reason = _banned_reason(path)
        if reason is None:
            continue

        bucket = "tracked" if _is_tracked_path(path, tracked) else "untracked"
        result[bucket].setdefault(reason, []).append(path.relative_to(ROOT))

        if path.is_dir():
            reported_banned_dirs.append(path)

    return result


def _format_findings(title: str, findings: dict[str, list[Path]]) -> list[str]:
    if not findings:
        return [f"{title}: none"]

    lines = [f"{title}:"]
    for reason, paths in sorted(findings.items()):
        lines.append(f"- {reason}: {_preview(sorted(paths))}")
    return lines


@dataclass(frozen=True)
class FixtureReference:
    source_file: Path
    fixture_path: Path


def _fixture_references() -> list[FixtureReference]:
    references: list[FixtureReference] = []
    for test_file in _iter_test_files():
        references.extend(_fixture_references_in_test(test_file))
    return sorted(references, key=lambda ref: (ref.source_file, ref.fixture_path))


def _fixture_references_in_test(test_file: Path) -> list[FixtureReference]:
    try:
        source = test_file.read_text(encoding="utf-8")
        if FIXTURE_REFERENCE_SKIP_MARKER in source:
            return []
        tree = ast.parse(source, filename=str(test_file))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    references: set[Path] = set()
    fixture_names = _fixture_dir_names(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = _path_join_parts(node)
            if parts and _parts_reference_fixture_file(parts):
                references.add(_resolve_fixture_parts(test_file, parts))
                continue

            if (
                isinstance(node.left, ast.Name)
                and node.left.id in fixture_names
                and isinstance(node.right, ast.Constant)
                and isinstance(node.right.value, str)
            ):
                references.add((test_file.parent / FIXTURE_DIR_NAME / node.right.value).resolve())
                continue

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            direct = _fixture_path_from_string(test_file, node.value)
            if direct is not None:
                references.add(direct)

    return [
        FixtureReference(source_file=test_file.resolve(), fixture_path=fixture)
        for fixture in sorted(references)
    ]


def _fixture_dir_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        parts = _path_join_parts(node.value)
        if not parts or parts[-1] != FIXTURE_DIR_NAME:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _parts_reference_fixture_file(parts: tuple[str, ...]) -> bool:
    if FIXTURE_DIR_NAME not in parts:
        return False
    return parts.index(FIXTURE_DIR_NAME) < len(parts) - 1


def _path_join_parts(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _path_join_parts(node.left)
        right = _path_join_parts(node.right)
        if left is None or right is None:
            return None
        return (*left, *right)

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)

    if _is_test_file_parent_expr(node):
        return ("__TEST_PARENT__",)

    return None


def _is_test_file_parent_expr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "parent"
        and _is_path_dunder_file_expr(node.value)
    )


def _is_path_dunder_file_expr(node: ast.AST) -> bool:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Path"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "__file__"
    ):
        return True

    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "resolve"
        and isinstance(node.func.value, ast.Call)
        and _is_path_dunder_file_expr(node.func.value)
    )


def _resolve_fixture_parts(test_file: Path, parts: tuple[str, ...]) -> Path:
    if parts[0] == "__TEST_PARENT__":
        return test_file.parent.joinpath(*parts[1:]).resolve()
    return ROOT.joinpath(*parts).resolve()


def _fixture_path_from_string(test_file: Path, value: str) -> Path | None:
    normalized = value.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if FIXTURE_DIR_NAME not in parts:
        return None

    fixture_index = parts.index(FIXTURE_DIR_NAME)
    if fixture_index == len(parts) - 1:
        return None
    if fixture_index == 0:
        return test_file.parent.joinpath(*parts).resolve()
    return ROOT.joinpath(*parts).resolve()


def _find_untracked_fixture_references() -> list[str]:
    tracked = {path.resolve() for path in _git_tracked_files()}
    problems: list[str] = []

    for reference in _fixture_references():
        source_rel = reference.source_file.relative_to(ROOT)
        try:
            fixture_rel = reference.fixture_path.relative_to(ROOT)
        except ValueError:
            fixture_rel = reference.fixture_path

        if not reference.fixture_path.exists():
            problems.append(f"{source_rel} references missing fixture {fixture_rel}")
        elif not _fixture_path_is_tracked(reference.fixture_path, tracked):
            problems.append(f"{source_rel} references untracked fixture {fixture_rel}")

    return problems


def _fixture_path_is_tracked(fixture_path: Path, tracked: set[Path]) -> bool:
    resolved = fixture_path.resolve()
    if resolved in tracked:
        return True
    if resolved.is_dir():
        return any(resolved in tracked_path.parents for tracked_path in tracked)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tracked-only",
        action="store_true",
        help="Fail only on tracked banned artifacts; report untracked artifacts as warnings.",
    )
    args = parser.parse_args(argv)

    problems: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_ROOT_DOCS:
        if not (ROOT / rel).exists():
            problems.append(f"missing required root document: {rel}")

    findings = _classify_findings()
    tracked_findings = findings["tracked"]
    untracked_findings = findings["untracked"]

    if tracked_findings:
        problems.extend(_format_findings("Tracked banned artifacts", tracked_findings))

    if untracked_findings:
        formatted_untracked = _format_findings("Untracked banned artifacts", untracked_findings)
        if args.tracked_only:
            warnings.extend(formatted_untracked)
        else:
            problems.extend(formatted_untracked)

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

    untracked_fixtures = _find_untracked_fixture_references()
    if untracked_fixtures:
        problems.append("Referenced fixture files must be tracked:")
        problems.extend(f"- {problem}" for problem in untracked_fixtures)

    if warnings:
        print("Publication hygiene warnings:")
        for warning in warnings:
            print(warning)

    if problems:
        print("Publication hygiene check failed:")
        for problem in problems:
            print(problem)
        return 1

    print("Publication hygiene check passed.")
    print("Mode:", "tracked-only" if args.tracked_only else "strict")
    print("Required root docs present:", ", ".join(REQUIRED_ROOT_DOCS))
    print("Tracked banned artifacts: none")
    if args.tracked_only:
        print("Untracked banned artifacts do not fail in tracked-only mode.")
    else:
        print("Untracked banned artifacts: none")
    print("Legacy package READMEs are confined to docs/history/.")
    print("Referenced fixture files are tracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
