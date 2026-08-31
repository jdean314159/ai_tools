from __future__ import annotations

import json
import hashlib
from pathlib import Path
from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats
from examples.engram_memory_security_probe import cases, run_experiment, suite_digest


class DefensiveSyntheticEngine:
    model = "/private/synthetic.gguf"

    def generate(self, request):
        prompt = request.messages[0].content
        case = next(case for case in cases() if case.question in prompt)
        payload = {"value": case.expected_value, "evidence_id": case.trusted_id}
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=json.dumps(payload)),
            finish_reason="stop",
            usage=UsageStats(input_tokens=100, output_tokens=8, latency_ms=1.0),
            model_name=self.model,
            backend="synthetic",
            seed_status="accepted",
        )


def test_security_suite_attributes_missing_trust_enforcement(tmp_path):
    body = run_experiment(DefensiveSyntheticEngine(), memory_root=tmp_path)
    assert len(cases()) == 5 and suite_digest().startswith("sha256:")
    assert body["poison_storage_count"] == 5
    assert body["poison_retrieval_count"] == 5
    assert body["poison_prompt_count"] == 5
    assert body["answer_correct_count"] == 5
    assert body["summary"]["primary_failure_counts"]["storage"] == 5


def test_security_artifact_omits_raw_content(tmp_path):
    encoded = json.dumps(run_experiment(DefensiveSyntheticEngine(), memory_root=tmp_path))
    for forbidden in (
        "/private/",
        "192.168.50.225",
        "ignore all other memory",
        "support code ALPHA",
    ):
        assert forbidden not in encoded


def test_committed_security_artifact_is_pinned_and_private():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/projects/runs/2026-08-30-spark-qwen-engram-memory-security-v1.json"
    )
    content = path.read_bytes()
    assert (
        hashlib.sha256(content).hexdigest()
        == "3d829d10a25ee0edef7ce358a96b7c5dd86856b5f5ac4182c4e85b87edd2995e"
    )
    decoded = content.decode()
    for forbidden in (
        "192.168.50.225",
        "/home/",
        "ignore all other memory",
        "support code ALPHA",
        "Dormant imported",
    ):
        assert forbidden not in decoded
