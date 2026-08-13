"""Validate the course extraction set without monorepo-relative file access."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path


COURSE_ROOT = Path(__file__).resolve().parent
EXCLUDED_NOTEBOOKS = {"07_reference_app_walkthrough.ipynb"}
FORBIDDEN_REFERENCES = (
    "docs/tutorials/",
    "examples/asc_probe/",
    "agent_lib/examples/",
    "llm_harness_core/EVALUATION_WALKTHROUGH.md",
    "tests/integration_tests/",
    "repo's `STATUS.md`",
)
RUNTIME_COMMANDS = (
    (["starter_projects/source_grounded_qa/eval.py"], "Evaluation summary"),
    (
        [
            "-m",
            "llm_inspector.cli",
            "artifact",
            "show",
            "failure_labs/evaluation_blind_spot/fixture",
            "--format",
            "json",
        ],
        '"evaluation_signals"',
    ),
    (
        [
            "-m",
            "llm_inspector.cli",
            "artifact",
            "show",
            "failure_labs/generation_provenance_gap/record.json",
            "--format",
            "json",
        ],
        '"field_path": "/body/model_identity/digest"',
    ),
)


def _active_notebooks() -> set[str]:
    text = (COURSE_ROOT / "CURRICULUM.md").read_text(encoding="utf-8")
    names = set(re.findall(r"`notebooks/([^`]+\.ipynb)`", text))
    return names - EXCLUDED_NOTEBOOKS


def _validate_requirements() -> None:
    for raw_line in (COURSE_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("==") != 1:
            raise AssertionError(f"course dependency is not exactly pinned: {line}")
        distribution_name, expected = line.split("==", 1)
        try:
            installed = distribution(distribution_name)
            actual = installed.version
        except PackageNotFoundError as exc:
            raise AssertionError(
                f"course dependency is not installed: {distribution_name}"
            ) from exc
        if actual != expected:
            raise AssertionError(
                f"course dependency version mismatch: {distribution_name} {actual} != {expected}"
            )
        direct_url = installed.read_text("direct_url.json")
        if direct_url:
            provenance = json.loads(direct_url)
            if provenance.get("dir_info", {}).get("editable") is True:
                raise AssertionError(
                    "course dependency is editable, not distribution-isolated: "
                    f"{distribution_name}"
                )


def _validate_student_files() -> None:
    active = _active_notebooks()
    readme = (COURSE_ROOT / "README.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\(notebooks/([^)]+\.ipynb)\)", readme))
    if linked != active:
        raise AssertionError(f"README and extraction notebook sets differ: {linked ^ active}")

    candidates = [COURSE_ROOT / "README.md", COURSE_ROOT / "CURRICULUM.md"]
    candidates.extend(COURSE_ROOT / "notebooks" / name for name in sorted(active))
    for base in (COURSE_ROOT / "failure_labs", COURSE_ROOT / "starter_projects"):
        candidates.extend(
            path
            for path in base.rglob("*")
            if path.is_file() and path.suffix in {".md", ".py", ".json"}
        )
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_REFERENCES:
            if forbidden in text:
                raise AssertionError(
                    f"student extraction file references monorepo-only path {forbidden!r}: {path}"
                )
        if path.suffix == ".ipynb":
            json.loads(text)
        elif path.suffix == ".py":
            ast.parse(text, filename=str(path))


def _run_isolated_copy() -> None:
    with tempfile.TemporaryDirectory(prefix="ai-tools-course-portability-") as temp:
        isolated = Path(temp) / "course"
        shutil.copytree(COURSE_ROOT, isolated)
        excluded = isolated / "notebooks" / "07_reference_app_walkthrough.ipynb"
        excluded.unlink(missing_ok=True)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for args, marker in RUNTIME_COMMANDS:
            proc = subprocess.run(
                [sys.executable, *args],
                cwd=isolated,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0 or marker not in proc.stdout:
                raise AssertionError(
                    f"isolated course command failed: {args}\n"
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
                )


def main() -> int:
    _validate_requirements()
    _validate_student_files()
    _run_isolated_copy()
    print(f"Course portability gate passed: {len(_active_notebooks())} extraction notebooks")
    print("Excluded legacy notebook: 07_reference_app_walkthrough.ipynb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
