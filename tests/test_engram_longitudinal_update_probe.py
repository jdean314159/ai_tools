from __future__ import annotations

import json
import hashlib
from pathlib import Path

from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats

from examples.engram_longitudinal_update_probe import run_experiment, timelines


class SyntheticLedgerEngine:
    model = "/private/synthetic.gguf"

    def generate(self, request):
        prompt = request.messages[0].content
        probe = next(p for t in timelines() for p in t.probes if p.question in prompt)
        payload = {"value": probe.expected_value, "evidence_id": probe.expected_evidence_id}
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=json.dumps(payload)),
            finish_reason="stop",
            usage=UsageStats(input_tokens=30, output_tokens=8, latency_ms=1.0),
            model_name=self.model,
            backend="synthetic",
            seed_status="accepted",
        )


def test_frozen_longitudinal_probe_attributes_all_stages(tmp_path):
    body = run_experiment(SyntheticLedgerEngine(), memory_root=tmp_path)
    assert body["oracle_or_llm_judge_used"] is False
    assert body["probe_count"] == 7
    assert body["storage_pass_count"] == 7
    assert body["retrieval_pass_count"] == 7
    assert body["end_to_end_pass_count"] == 7


def test_artifact_body_omits_endpoint_paths_and_raw_memory(tmp_path):
    encoded = json.dumps(run_experiment(SyntheticLedgerEngine(), memory_root=tmp_path))
    for forbidden in ("/private/", "192.168.50.225", "Correction:", "Retraction:"):
        assert forbidden not in encoded


def test_committed_longitudinal_artifact_is_pinned_and_private():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/projects/runs/2026-08-30-spark-qwen-engram-longitudinal-v1.json"
    )
    content = path.read_bytes()
    assert (
        hashlib.sha256(content).hexdigest()
        == "3964ca640a340b9365ab49d77fea1875258bcefaeebace7ad809ac2ac96c3b7d"
    )
    decoded = content.decode()
    for forbidden in ("192.168.50.225", "/home/", "Correction:", "Retraction:", "Question:"):
        assert forbidden not in decoded
