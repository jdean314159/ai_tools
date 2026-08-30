from __future__ import annotations

import hashlib
import json
from pathlib import Path

from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats

from examples.engram_procedural_components_probe import EXPECTED, cases, run_experiment


class SyntheticEngine:
    model = "/private/synthetic.gguf"
    def generate(self, request):
        prompt = request.messages[0].content
        case = next(case for case in cases() if case.query in prompt)
        payload = {"components": EXPECTED[case.case_id], "evidence_id": case.experience_id}
        return GenerationResponse(message=ChatMessage(role="assistant", content=json.dumps(payload)),
            finish_reason="stop", usage=UsageStats(input_tokens=100, output_tokens=12, latency_ms=1.0),
            model_name=self.model, backend="synthetic", seed_status="accepted")


def test_component_suite_scores_five_exact_cases(tmp_path):
    body = run_experiment(SyntheticEngine(), memory_root=tmp_path)
    assert body["oracle_or_llm_judge_used"] is False
    assert body["storage_pass_count"] == 5
    assert body["retrieval_pass_count"] == 5
    assert body["component_pass_count"] == 5
    assert body["end_to_end_pass_count"] == 5
    assert all(item["selected_count"] < item["declared_count"] for item in body["observations"])


def test_component_artifact_omits_raw_inputs_and_private_data(tmp_path):
    encoded = json.dumps(run_experiment(SyntheticEngine(), memory_root=tmp_path))
    for forbidden in ("/private/", "192.168.50.225", "Prior incident:", "Question:"):
        assert forbidden not in encoded


def test_committed_component_artifact_is_pinned_and_private():
    path = Path(__file__).resolve().parents[1] / "docs/projects/runs/2026-08-30-spark-qwen-engram-procedural-components-v1.json"
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == "1eb4fadc613008e48e75706506d3090b9dc81eeb8a0ef01f2ac4aa50cbf57b10"
    decoded = content.decode()
    for forbidden in ("192.168.50.225", "/home/", "Prior incident:", "Question:"):
        assert forbidden not in decoded
