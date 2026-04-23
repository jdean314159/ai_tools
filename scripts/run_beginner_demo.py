from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_step(label: str, rel_path: str) -> None:
    target = REPO_ROOT / rel_path
    print(f"\n=== {label} ===")
    print(f"Running: {target}")
    subprocess.run([sys.executable, str(target)], check=True, cwd=REPO_ROOT)


def main() -> None:
    print("Beginner demo")
    print(f"Repo root: {REPO_ROOT}")

    run_step("Minimal chat app", "course/starter_projects/minimal_chat_app/main.py")
    run_step("Source-grounded QA evaluation", "course/starter_projects/source_grounded_qa/eval.py")

    print("\nBeginner demo complete.")


if __name__ == "__main__":
    main()
