from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_evaluation_walkthrough_mentions_baseline_and_augmented_comparisons() -> None:
    guide = ROOT / "llm_harness_core" / "EVALUATION_WALKTHROUGH.md"
    text = guide.read_text(encoding="utf-8")

    assert "baseline" in text.lower()
    assert "augmented" in text.lower()
    assert "evidence presence" in text.lower()
