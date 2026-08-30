from __future__ import annotations

import json
import hashlib
from pathlib import Path

from examples.engram_trust_prompt_pressure_probe import EXPECTED_VALUE, RELEVANT_ID, run_experiment
from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats


class ExactSyntheticEngine:
    model = "/private/synthetic.gguf"

    def generate(self, request):
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=json.dumps({
                "value": EXPECTED_VALUE, "evidence_id": RELEVANT_ID,
            })), finish_reason="stop",
            usage=UsageStats(input_tokens=100, output_tokens=8, latency_ms=1.0),
            model_name=self.model, backend="synthetic", seed_status="accepted",
        )


def test_prompt_pressure_profile_attributes_displacement_and_preserves_anchor(tmp_path):
    body = run_experiment(ExactSyntheticEngine(), memory_root=tmp_path)

    assert body["case_count_per_condition"] == 9
    assert body["acceptance_gate"]["passed"] is True
    assert body["pressure_observed"] is True
    assert all(
        item["conditions"][condition]["retrieval_passed"]
        for item in body["observations"] for condition in ("policy_off", "policy_on")
    )
    assert all(
        item["conditions"][condition]["ingestion_accepted_count"] == item["memory_count"]
        for item in body["observations"] for condition in ("policy_off", "policy_on")
    )
    assert all(
        item["conditions"][condition]["composition_passed"]
        for item in body["observations"] for condition in ("policy_off", "policy_on")
    )
    assert any(item["policy_on_inclusion_delta"] < 0 for item in body["observations"])


def test_prompt_pressure_artifact_is_privacy_minimized(tmp_path):
    encoded = json.dumps(run_experiment(ExactSyntheticEngine(), memory_root=tmp_path))
    for forbidden in ("/private/", "192.168.50.225", "Approved Anchor decision", "Marigold handbook"):
        assert forbidden not in encoded


def test_committed_prompt_pressure_artifacts_are_pinned_and_private():
    root = Path(__file__).resolve().parents[1] / "docs" / "projects" / "runs"
    expected = {
        "2026-08-30-spark-qwen-engram-trust-prompt-pressure-v1.json":
            "2a6bac3dae16ba6b36cfd0889125c15c36e4a828406ace8849ad62cc83b4095e",
        "2026-08-30-spark-qwen-engram-trust-prompt-pressure-v2.json":
            "112200a73480e4330667576aba5a172ead137bec0680945978c61c4a1ae913e8",
        "2026-08-30-spark-qwen-engram-trust-prompt-pressure-v3.json":
            "5b2bd4f97355044da97fc8d733fa713071cd43c74d80529c9c0ab74328381765",
    }
    for name, digest in expected.items():
        content = (root / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        decoded = content.decode()
        for forbidden in ("192.168.50.225", "/home/", "Approved Anchor decision", "CERULEAN"):
            assert forbidden not in decoded
