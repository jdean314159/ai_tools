from __future__ import annotations

import json
import hashlib
from pathlib import Path

from examples.llm_context_retention_probe import END_VALUE, START_VALUE, build_artifact, run_experiment
from llm_engines import ChatMessage, GenerationResponse
from llm_engines.contracts import UsageStats
from llm_harness_core import artifact_to_dict


class RetainingEngine:
    BACKEND = "synthetic"
    model = "/private/synthetic.gguf"

    def generate(self, request):
        words = len((request.messages[0].content or "").split())
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=json.dumps({"start": START_VALUE, "end": END_VALUE})),
            finish_reason="stop", usage=UsageStats(input_tokens=words + 7, output_tokens=8, latency_ms=1.0),
            model_name=self.model, backend="synthetic", seed_status="accepted",
        )


def test_context_retention_profile_passes_exact_and_monotonic_gates():
    body = run_experiment(RetainingEngine())
    assert body["acceptance_gate"]["passed"] is True
    assert [item["status"] for item in body["results"]] == ["passed", "passed", "passed"]
    assert [item["input_tokens"] for item in body["results"]] == sorted(
        item["input_tokens"] for item in body["results"]
    )


def test_context_retention_artifact_omits_raw_content_and_paths():
    encoded = json.dumps(artifact_to_dict(build_artifact(run_experiment(RetainingEngine()))))
    for forbidden in ("/private/", "ALPHA7", "OMEGA9", "context context context"):
        assert forbidden not in encoded


def test_committed_context_retention_artifact_is_pinned_and_private():
    path = (
        Path(__file__).resolve().parents[1] / "docs" / "projects" / "llm_engines" / "runs"
        / "2026-08-31-spark-qwen38-flash-next-context-retention-v1.json"
    )
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == "adfaab32d1b04de829212bf3831bf69ecf35d84eca0f387f566082f5d59575eb"
    decoded = content.decode()
    for forbidden in ("192.168.50.225", "/home/", "ALPHA7", "OMEGA9", "context context context"):
        assert forbidden not in decoded
