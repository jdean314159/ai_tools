"""Build local wheels and run the course gate in a non-editable environment."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIRS = (
    "llm_harness_core",
    "llm_engines",
    "engram",
    "llm_inspector",
    "rag_lib",
    "llm_inspector_ui",
    "agent_lib",
    "action_trajectory_loop_guard",
    "examples/language_tutor_reference_app",
)


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    proc = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ai-tools-course-dist-") as temp:
        base = Path(temp)
        wheels = base / "wheels"
        wheels.mkdir()
        sources = base / "sources"
        sources.mkdir()
        for package_dir in PACKAGE_DIRS:
            source_copy = sources / package_dir
            source_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                ROOT / package_dir,
                source_copy,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.egg-info",
                    "build",
                    ".pytest_cache",
                    ".ruff_cache",
                ),
            )
            _run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    str(wheels),
                    str(source_copy),
                ],
                cwd=sources,
            )

        environment = base / "venv"
        base_python = str(getattr(sys, "_base_executable", sys.executable))
        _run(
            [base_python, "-m", "venv", "--system-site-packages", str(environment)],
            cwd=ROOT,
        )
        python = environment / "bin" / "python"
        inner_site = environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        outer_site = Path(site.getsitepackages()[0]).resolve()
        (inner_site / "third_party_test_dependencies.pth").write_text(
            f"{outer_site}\n",
            encoding="utf-8",
        )
        wheel_paths = [str(path) for path in sorted(wheels.glob("*.whl"))]
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--force-reinstall",
                *wheel_paths,
            ],
            cwd=ROOT,
        )

        isolated_course = base / "course"
        shutil.copytree(ROOT / "course", isolated_course)
        clean_env = dict(os.environ)
        clean_env.pop("PYTHONPATH", None)
        clean_env["PYTHONDONTWRITEBYTECODE"] = "1"
        _run([str(python), "check_portability.py"], cwd=isolated_course, env=clean_env)

    print("Course distribution portability gate passed with locally built wheels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
