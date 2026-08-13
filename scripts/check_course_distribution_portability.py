"""Build local wheels and run the course gate in a non-editable environment."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
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
        for package_dir in PACKAGE_DIRS:
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
                    str(ROOT / package_dir),
                ],
                cwd=ROOT,
            )

        environment = base / "venv"
        _run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(environment)],
            cwd=ROOT,
        )
        python = environment / "bin" / "python"
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
