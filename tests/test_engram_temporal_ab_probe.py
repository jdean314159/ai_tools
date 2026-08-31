from __future__ import annotations

import hashlib
import json
from pathlib import Path

from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats

from examples.engram_temporal_ab_probe import run_experiment, timelines


class SyntheticEngine:
    model = "/private/synthetic.gguf"

    def generate(self, request):
        prompt = request.messages[0].content
        query = next(
            query
            for timeline in timelines()
            for query in timeline.queries
            if query.question in prompt
        )
        payload = {"value": query.expected_value, "evidence_id": query.expected_evidence_id}
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=json.dumps(payload)),
            finish_reason="stop",
            usage=UsageStats(input_tokens=80, output_tokens=8, latency_ms=1.0),
            model_name=self.model,
            backend="synthetic",
            seed_status="accepted",
        )


def test_temporal_arm_removes_obsolete_current_evidence_and_keeps_history(tmp_path):
    body = run_experiment(SyntheticEngine(), memory_root=tmp_path)
    assert body["current_obsolete_prompt_counts"] == {"legacy": 3, "temporal": 0}
    assert body["arm_summaries"]["legacy"]["primary_failure_counts"]["composition"] == 3
    assert body["arm_summaries"]["temporal"]["end_to_end_pass_count"] == 5
    historical = [
        item for item in body["observations"] if item["arm"] == "temporal" and item["historical"]
    ]
    assert len(historical) == 2
    assert all(item["end_to_end_passed"] for item in historical)


def test_temporal_ab_artifact_is_privacy_minimized(tmp_path):
    encoded = json.dumps(run_experiment(SyntheticEngine(), memory_root=tmp_path))
    for forbidden in ("/private/", "192.168.50.225", "Return JSON only", "deployment region was"):
        assert forbidden not in encoded


def test_committed_temporal_ab_artifact_is_pinned_and_private():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/projects/runs/2026-08-30-spark-qwen-engram-temporal-ab-v1.json"
    )
    content = path.read_bytes()
    assert (
        hashlib.sha256(content).hexdigest()
        == "7952ebd3693fcde4941fd0dd8422cb75a835ea4e262e17b8dc57c5eb73c2de94"
    )
    decoded = content.decode()
    for forbidden in (
        "192.168.50.225",
        "/home/",
        "Return JSON only",
        "deployment region was",
        "Retraction:",
    ):
        assert forbidden not in decoded
