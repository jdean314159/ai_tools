from __future__ import annotations

import json
import hashlib
from pathlib import Path

from examples.engram_memory_security_probe import cases
from examples.engram_memory_security_policy_probe import run_experiment
from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats


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
            model_name=self.model, backend="synthetic", seed_status="accepted",
        )


def test_policy_pair_blocks_poison_before_prompt(tmp_path):
    body = run_experiment(DefensiveSyntheticEngine(), memory_root=tmp_path)
    off = body["conditions"]["policy_off"]
    on = body["conditions"]["policy_on"]
    assert off["poison_storage_count"] == 5
    assert off["poison_retrieval_count"] == 5
    assert off["poison_prompt_count"] == 5
    assert on["poison_storage_count"] == 0
    assert on["poison_retrieval_count"] == 0
    assert on["poison_prompt_count"] == 0
    assert on["answer_correct_count"] == 5
    assert on["value_correct_count"] == 5
    assert on["citation_correct_count"] == 5
    assert body["acceptance_gate"]["security_passed"] is True
    assert body["acceptance_gate"]["utility_passed"] is True
    assert body["acceptance_gate"]["passed"] is True


def test_policy_pair_artifact_is_privacy_minimized(tmp_path):
    encoded = json.dumps(run_experiment(DefensiveSyntheticEngine(), memory_root=tmp_path))
    for forbidden in (
        "/private/", "192.168.50.225", "ignore all other memory",
        "support code ALPHA", "cross tenant poison",
    ):
        assert forbidden not in encoded


def test_committed_policy_artifacts_are_pinned_and_private():
    root = Path(__file__).resolve().parents[1]
    expected = {
        "2026-08-30-spark-qwen-engram-memory-security-policy-v2.json":
            "a67d6d37252737073a850efcc7d5451efdfa40e9e2a9cba9978386e67c6f5bce",
        "2026-08-30-spark-qwen-engram-memory-security-policy-v3.json":
            "714548066045ac2c4a19822ed72ea0172e262d841374cf0f51e0bb7aad033214",
        "2026-08-30-spark-qwen-engram-memory-security-policy-v4.json":
            "2f9b2e8565598a6e99498cd84cf1ff3aa0470813b1a4c62df3aa03c52e3f2a31",
    }
    for name, digest in expected.items():
        content = (root / "docs" / "projects" / "runs" / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        decoded = content.decode()
        for forbidden in ("192.168.50.225", "/home/", "ignore all other memory"):
            assert forbidden not in decoded
