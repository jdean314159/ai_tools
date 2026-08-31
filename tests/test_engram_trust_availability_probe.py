import json
import hashlib
from pathlib import Path

from examples.engram_trust_availability_probe import cases, run_experiment
from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats


class ExactSyntheticEngine:
    model = "/private/synthetic.gguf"

    def generate(self, request):
        prompt = request.messages[0].content
        case = next(case for case in cases() if case.question in prompt)
        return GenerationResponse(
            message=ChatMessage(
                role="assistant",
                content=json.dumps(
                    {
                        "value": case.value,
                        "evidence_id": case.evidence_id,
                    }
                ),
            ),
            finish_reason="stop",
            usage=UsageStats(input_tokens=100, output_tokens=8, latency_ms=1.0),
            model_name=self.model,
            backend="synthetic",
            seed_status="accepted",
        )


def test_availability_suite_separates_false_positives_from_workflow_blocks(tmp_path):
    body = run_experiment(ExactSyntheticEngine(), memory_root=tmp_path)
    assert body["must_accept_count"] == 3
    assert body["false_positive_count"] == 0
    assert body["availability_blocked_count"] == 5
    assert body["accepted_exact_output_count"] == 3
    assert body["acceptance_gate"]["passed"] is True
    outcomes = {item["case_id"]: item for item in body["observations"]}
    assert outcomes["legacy_unlabeled"]["expected_policy_action"] == "migration_required"
    assert outcomes["reviewed_quarantine"]["expected_policy_action"] == "release_required"


def test_availability_artifact_omits_raw_content(tmp_path):
    encoded = json.dumps(run_experiment(ExactSyntheticEngine(), memory_root=tmp_path))
    for forbidden in (
        "/private/",
        "192.168.50.225",
        "approved color is BLUE",
        "suggested color is GOLD",
    ):
        assert forbidden not in encoded


def test_committed_availability_artifact_is_pinned_and_private():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/projects/runs/2026-08-30-spark-qwen-engram-trust-availability-v1.json"
    )
    content = path.read_bytes()
    assert (
        hashlib.sha256(content).hexdigest()
        == "1e235079bbba922bc183147cd13bf5948bd164afa171ed0d7e0e9ecd7a5daa62"
    )
    decoded = content.decode()
    for forbidden in ("192.168.50.225", "/home/", "approved color is", "suggested color is"):
        assert forbidden not in decoded
