"""Regression tests for the repository-level pytest bootstrap."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_root_conftest_does_not_eagerly_import_source_packages() -> None:
    script = f"""
import importlib.util
import sys

root = {str(REPO_ROOT)!r}
sys.path.insert(0, root)
spec = importlib.util.spec_from_file_location("repo_test_bootstrap", root + "/conftest.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
unexpected = sorted(set(module.SOURCE_PACKAGE_EXPECTATIONS).intersection(sys.modules))
if unexpected:
    raise SystemExit("eagerly imported source packages: " + ", ".join(unexpected))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
