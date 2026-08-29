from __future__ import annotations

import json

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
    assert [probe.status for probe in report.probes] == ["passed"] * 4
    encoded = report.to_json()
    assert "Reply with exactly" not in encoded
    assert "CHARACTERIZATION_OK" not in encoded
    assert "SIGNAL" not in encoded


def test_characterization_marks_unavailable_features_unsupported():
    from llm_engines.backends.mock import MockEngine

    report = characterize_engine(
        MockEngine(response_fn=lambda request: "CHARACTERIZATION_OK")
    )

    assert [probe.status for probe in report.probes] == [
        "passed",
        "unsupported",
        "unsupported",
        "unsupported",
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
