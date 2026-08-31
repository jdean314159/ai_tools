from __future__ import annotations

import json
import hashlib
from pathlib import Path

from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats

from examples.memory_inspection_probe import build_artifact, cases, run_experiment


class SyntheticEngine:
    model = "/private/models/synthetic.gguf"

    def generate(self, request):
        prompt = request.messages[0].content
        match = next((case for case in cases() if case.relevant_id in prompt), None)
        payload = (
            {"value": match.value, "memory_id": match.relevant_id}
            if match
            else {"value": "UNKNOWN", "memory_id": "NONE"}
        )
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=json.dumps(payload)),
            finish_reason="stop",
            usage=UsageStats(input_tokens=20, output_tokens=8, latency_ms=4.0),
            model_name=self.model,
            backend="synthetic",
            seed_status="accepted",
        )


def test_memory_composition_scores_five_grounded_pairs(tmp_path):
    body = run_experiment(SyntheticEngine(), memory_root=tmp_path)

    assert body["case_count"] == 5
    assert body["baseline_safe_count"] == 5
    assert body["memory_correct_count"] == 5
    assert body["paired_success_count"] == 5
    assert body["distractor_used_count"] == 0
    memory = [item for item in body["observations"] if item["condition"] == "memory"]
    assert all(item["relevant_selected"] for item in memory)
    assert all(item["relevant_in_prompt"] for item in memory)


def test_artifact_omits_raw_interactions_and_private_paths(tmp_path):
    body = run_experiment(SyntheticEngine(), memory_root=tmp_path)
    artifact = build_artifact(body)
    encoded = json.dumps(artifact.body)

    assert artifact.envelope.profile == "examples.memory_inspection_composition"
    assert artifact.envelope.profile_version == 2
    assert artifact.body["prior_unretained_attempts"] == 2
    assert artifact.envelope.execution_environment["model_label"] == "synthetic.gguf"
    for forbidden in (
        "/private/",
        "Current authoritative fact",
        "Superseded draft",
        "What is Project",
    ):
        assert forbidden not in encoded


def test_committed_memory_inspection_artifact_is_pinned_and_private():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/projects/runs/2026-08-30-spark-qwen-memory-inspection-v2.json"
    )
    content = path.read_bytes()

    assert (
        hashlib.sha256(content).hexdigest()
        == "1fc7e20b98875e3e7128337dea6b78e9d387a556d0541a80bbb9248e2384055c"
    )
    decoded = content.decode()
    for forbidden in (
        "192.168.50.225",
        "/home/",
        "Current authoritative fact",
        "Superseded draft",
        "Question:",
    ):
        assert forbidden not in decoded
