from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_evaluation_walkthrough_mentions_baseline_and_augmented_comparisons() -> None:
    guide = ROOT / "llm_harness_core" / "EVALUATION_WALKTHROUGH.md"
    text = guide.read_text(encoding="utf-8")

    assert "baseline" in text.lower()
    assert "augmented" in text.lower()
    assert "course/notebooks/07_evaluating_llm_applications.ipynb" in text


def test_source_grounded_qa_eval_prints_evaluation_summary() -> None:
    script = ROOT / "course" / "starter_projects" / "source_grounded_qa" / "eval.py"
    proc = subprocess.run([sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr
    assert "Evaluation summary" in proc.stdout
    assert "Answer uplift" in proc.stdout
