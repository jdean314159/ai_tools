from __future__ import annotations

import hashlib
from pathlib import Path

from examples.engram_temporal_vector_cold_probe import cases, suite_digest


def test_temporal_vector_cold_suite_is_frozen_and_distinct():
    suite = cases()
    assert len(suite) == 3
    assert len({case.topic_key for case in suite}) == 3
    assert all(case.old_id != case.current_id for case in suite)
    assert {case.current_action for case in suite} == {"update", "retract"}
    assert suite_digest().startswith("sha256:")


def test_committed_temporal_vector_cold_artifact_is_pinned_and_private():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/projects/runs/2026-08-30-engram-temporal-vector-cold-v1.json"
    )
    content = path.read_bytes()
    assert (
        hashlib.sha256(content).hexdigest()
        == "0f49ef95c0c84f26bf5f377753056884d7191c92154e3723ede79c20ab4d5634"
    )
    decoded = content.decode()
    for forbidden in ("/home/", "cybernaif", "Virginia", "Frankfurt", "Where do", "Retraction:"):
        assert forbidden not in decoded
