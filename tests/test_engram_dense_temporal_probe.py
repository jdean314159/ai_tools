from __future__ import annotations

import hashlib
import json
from pathlib import Path

from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats

from examples.engram_dense_temporal_probe import cases, distractors, run_experiment


class SyntheticEngine:
    model = "/private/synthetic.gguf"

    def generate(self, request):
        prompt = request.messages[0].content
        case = next(case for case in cases() if case.question in prompt)
        payload = {"value": case.expected_value, "evidence_id": case.expected_evidence_id}
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=json.dumps(payload)), finish_reason="stop",
            usage=UsageStats(input_tokens=100, output_tokens=8, latency_ms=1.0),
            model_name=self.model, backend="synthetic", seed_status="accepted",
        )


def test_dense_suite_is_frozen_and_places_retrieval_under_pressure(tmp_path):
    assert all(len(distractors(case)) == 48 for case in cases())
    body = run_experiment(SyntheticEngine(), memory_root=tmp_path)
    assert body["oracle_or_llm_judge_used"] is False
    assert body["case_count"] == 5
    assert body["storage_pass_count"] == 5
    assert all(item["selected_count"] < item["declared_count"] for item in body["observations"])


def test_dense_artifact_body_omits_private_and_raw_inputs(tmp_path):
    encoded = json.dumps(run_experiment(SyntheticEngine(), memory_root=tmp_path))
    for forbidden in ("/private/", "192.168.50.225", "Historical planning note", "Correction:", "Question:"):
        assert forbidden not in encoded


def test_committed_dense_artifact_is_pinned_and_private():
    path = Path(__file__).resolve().parents[1] / "docs/projects/runs/2026-08-30-spark-qwen-engram-dense-temporal-v1.json"
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == "69f13f437599b69c129c1e9170fa57087731900cfeb7f7444ac80ae2a3ab3a2a"
    decoded = content.decode()
    for forbidden in ("192.168.50.225", "/home/", "Historical planning note", "Correction:", "Retraction:", "Question:"):
        assert forbidden not in decoded
