from __future__ import annotations

from rag_lib.eval.broken_rag_lab import evaluate_repair, render_comparison


def test_broken_rag_lab_shows_failed_then_repaired_result():
    summary = evaluate_repair()
    assert summary["pipelines"]["broken-rag"]["passed"] is False
    assert summary["pipelines"]["repaired-rag"]["passed"] is True


def test_broken_rag_lab_render_includes_evidence_flow():
    text = render_comparison(
        "What region does Project Mercury deploy the nightly evaluation job to?"
    )
    assert "Evidence flow:" in text
    assert "broken-rag" in text
    assert "repaired-rag" in text
