from __future__ import annotations

from engram.eval.memory_contamination_lab import compare_scenario, evaluate_repair


def test_memory_contamination_lab_broken_vs_repaired_scores():
    summary = evaluate_repair()
    docs = summary["scenarios"]["docs_policy"]
    model = summary["scenarios"]["model_update"]

    assert docs["broken"]["passed"] is False
    assert docs["repaired"]["passed"] is True
    assert model["broken"]["passed"] is False
    assert model["repaired"]["passed"] is True


def test_memory_contamination_lab_render_shows_excluded_stale_alternative():
    text = compare_scenario("docs_policy")
    assert "Evidence flow:" in text
    assert "excluded reason=stale_alternative_suppressed" in text
    assert "Google Docs" in text
