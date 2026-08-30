from __future__ import annotations

import hashlib
import json
from pathlib import Path

from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats

from examples.engram_procedural_transfer_probe import cases, distractors, run_experiment


class SyntheticEngine:
    model = "/private/synthetic.gguf"

    def generate(self, request):
        prompt = request.messages[0].content
        case = next(case for case in cases() if case.query in prompt)
        payload = {"value": case.expected_action, "evidence_id": case.experience_id}
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=json.dumps(payload)), finish_reason="stop",
            usage=UsageStats(input_tokens=100, output_tokens=8, latency_ms=1.0),
            model_name=self.model, backend="synthetic", seed_status="accepted",
        )


def test_procedural_suite_is_frozen_and_selective(tmp_path):
    assert all(len(distractors(case)) == 36 for case in cases())
    body = run_experiment(SyntheticEngine(), memory_root=tmp_path)
    assert body["oracle_or_llm_judge_used"] is False
    assert body["case_count"] == 5
    assert body["storage_pass_count"] == 5
    assert all(item["selected_count"] < item["declared_count"] for item in body["observations"])


def test_procedural_artifact_omits_raw_inputs_and_private_data(tmp_path):
    encoded = json.dumps(run_experiment(SyntheticEngine(), memory_root=tmp_path))
    for forbidden in ("/private/", "192.168.50.225", "Prior incident:", "Question:"):
        assert forbidden not in encoded


def test_committed_procedural_artifact_is_pinned_and_private():
    path = Path(__file__).resolve().parents[1] / "docs/projects/runs/2026-08-30-spark-qwen-engram-procedural-transfer-v1.json"
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == "5bacd6a04b5ab252cdb7b584ae237066f8140a87b1eb4a038309771df8a7f146"
    decoded = content.decode()
    for forbidden in ("192.168.50.225", "/home/", "Prior incident:", "Question:"):
        assert forbidden not in decoded
