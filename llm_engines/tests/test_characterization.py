from __future__ import annotations

import json
import hashlib
from pathlib import Path

from llm_harness_core import artifact_from_dict, artifact_to_dict

from llm_engines.characterization import (
    CHARACTERIZATION_CAMPAIGN_PROFILE,
    CHARACTERIZATION_PROFILE,
    build_characterization_artifact,
    characterize_engine,
    characterize_engine_repeated,
)
from llm_engines.contracts import (
    ChatMessage,
    EngineCapabilities,
    GenerationResponse,
    LogprobResult,
    TokenLogprob,
    ToolCall,
    UsageStats,
)


class CharacterizableEngine:
    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            chat=True,
            structured_output=True,
            tool_calling=True,
            logprobs=True,
        )

    def generate(self, request):
        if request.json_schema:
            text = '{"code": 7}'
        else:
            text = "CHARACTERIZATION_OK"
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=text),
            finish_reason="stop",
            usage=UsageStats(input_tokens=8, output_tokens=3, total_tokens=11, latency_ms=2.5),
            model_name="synthetic-model",
            backend="synthetic-backend",
        )

    def generate_with_tools(self, request, available_tools):
        return GenerationResponse(
            message=ChatMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        call_id="call-1",
                        name="lookup_characterization_code",
                        arguments={"code": "CHAR-7"},
                    )
                ],
            ),
            finish_reason="tool_call",
            model_name="synthetic-model",
            backend="synthetic-backend",
        )

    def generate_with_logprobs(self, request, top_logprobs=0):
        return LogprobResult(
            text="SIGNAL",
            token_logprobs=[TokenLogprob(token="SIGNAL", logprob=-0.25)],
        )


def test_characterization_runs_supported_synthetic_probes_without_raw_content():
    report = characterize_engine(CharacterizableEngine())

    assert report.backend == "synthetic-backend"
    assert report.model_label == "synthetic-model"
    assert report.suite_version == 2
    assert report.thinking_requested is None
    assert [probe.status for probe in report.probes] == ["passed"] * 4
    encoded = report.to_json()
    assert "Reply with exactly" not in encoded
    assert "CHARACTERIZATION_OK" not in encoded
    assert "SIGNAL" not in encoded


def test_characterization_marks_features_not_declared_by_adapter():
    from llm_engines.backends.mock import MockEngine

    report = characterize_engine(
        MockEngine(response_fn=lambda request: "CHARACTERIZATION_OK")
    )

    assert [probe.status for probe in report.probes] == [
        "passed",
        "not_declared",
        "not_declared",
        "not_declared",
    ]


def test_characterization_errors_retain_only_exception_type():
    class BrokenEngine(CharacterizableEngine):
        def generate_with_tools(self, request, available_tools):
            raise RuntimeError("secret endpoint detail")

    report = characterize_engine(BrokenEngine())
    tool_result = next(item for item in report.probes if item.probe_id == "tool_call")

    assert tool_result.status == "error"
    assert tool_result.error_type == "RuntimeError"
    assert "secret endpoint detail" not in report.to_json()


def test_characterization_artifact_round_trips_and_declares_privacy():
    report = characterize_engine(CharacterizableEngine())
    artifact = build_characterization_artifact(report)
    restored = artifact_from_dict(artifact_to_dict(artifact))

    assert restored.envelope.profile == CHARACTERIZATION_PROFILE
    assert restored.envelope.profile_version == 2
    assert restored.envelope.kind == "experiment"
    assert restored.envelope.privacy.validation.status == "validated"
    assert restored.body["probes"][0]["probe_id"] == "chat_exact_text"
    serialized_body = json.dumps(restored.body)
    assert "CHARACTERIZATION_OK" not in serialized_body
    assert "Reply with exactly" not in serialized_body
    assert "secret endpoint detail" not in serialized_body


def test_repeated_characterization_summarizes_stability_and_latency():
    report = characterize_engine_repeated(CharacterizableEngine(), repetitions=3)

    assert report.suite == CHARACTERIZATION_CAMPAIGN_PROFILE
    assert report.repetitions == 3
    assert report.suite_version == 2
    assert len(report.runs) == 3
    chat = report.probe_aggregates["chat_exact_text"]
    assert chat["status_counts"] == {"passed": 3}
    assert chat["status_stable"] is True
    assert chat["pass_rate"] == 1.0
    assert chat["latency_ms"] == {
        "samples": 3,
        "minimum": 2.5,
        "median": 2.5,
        "maximum": 2.5,
    }
    summary = json.loads(report.summary_json())
    assert "runs" not in summary
    assert summary["repetitions"] == 3


def test_characterization_threads_thinking_and_expands_budget():
    class CapturingEngine(CharacterizableEngine):
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            return super().generate(request)

        def generate_with_tools(self, request, available_tools):
            self.requests.append(request)
            return super().generate_with_tools(request, available_tools)

        def generate_with_logprobs(self, request, top_logprobs=0):
            self.requests.append(request)
            return super().generate_with_logprobs(request, top_logprobs)

    engine = CapturingEngine()
    report = characterize_engine(engine, thinking=True)

    assert report.thinking_requested is True
    assert len(engine.requests) == 4
    assert all(request.thinking is True for request in engine.requests)
    assert all(request.max_tokens == 512 for request in engine.requests)


def test_characterization_sanitizes_absolute_model_label():
    class PathModelEngine(CharacterizableEngine):
        def generate(self, request):
            response = super().generate(request)
            return response.model_copy(
                update={"model_name": "/home/private/models/synthetic.gguf"}
            )

    report = characterize_engine(PathModelEngine())

    assert report.model_label == "synthetic.gguf"
    assert "/home/private" not in report.to_json()


def test_repeated_characterization_rejects_a_single_run():
    import pytest

    with pytest.raises(ValueError, match="at least 2"):
        characterize_engine_repeated(CharacterizableEngine(), repetitions=1)


def test_repeated_characterization_artifact_round_trips():
    report = characterize_engine_repeated(CharacterizableEngine(), repetitions=2)
    restored = artifact_from_dict(
        artifact_to_dict(build_characterization_artifact(report))
    )

    assert restored.envelope.profile == CHARACTERIZATION_CAMPAIGN_PROFILE
    assert restored.body["repetitions"] == 2
    assert restored.body["probe_aggregates"]["tool_call"]["pass_rate"] == 1.0


def test_committed_spark_artifacts_match_documented_bytes_and_privacy_boundary():
    repo = Path(__file__).resolve().parents[2]
    runs = repo / "docs" / "projects" / "llm_engines" / "runs"
    expected = {
        "2026-08-29-spark-qwen-characterization-v2.json":
            "c75cdade1a7ddac6e4e41f2fce299947a469672235255bacc435e956aaf8d591",
        "2026-08-29-spark-qwen-tool-decisions-thinking-off-v2.json":
            "74d2c9695bc93b98129891bc224a15aff64328458dd65b3ce1ed2686445ceb73",
        "2026-08-29-spark-qwen-tool-decisions-thinking-on-v2.json":
            "422cc712db194094ef94c10711a80d374732a1849f00446d3bc49273d41ff8ed",
    }
    forbidden = (
        "192.168.50.225",
        "/home/",
        "cybernaif",
        "Reply with exactly",
        "Use lookup_record",
        "REC-17",
        "CHAR-7",
    )

    for name, digest in expected.items():
        content = (runs / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        decoded = content.decode("utf-8")
        assert not any(value in decoded for value in forbidden)


def test_readme_uses_placeholder_endpoint_and_model_path():
    repo = Path(__file__).resolve().parents[2]
    readme = (repo / "llm_engines" / "README.md").read_text(encoding="utf-8")

    assert "http://inference-host:8080/v1" in readme
    assert "192.168.50.225" not in readme
    assert "/home/cybernaif" not in readme
