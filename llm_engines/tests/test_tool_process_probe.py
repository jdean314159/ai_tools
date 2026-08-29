from __future__ import annotations

import json

import pytest
from llm_harness_core import artifact_from_dict, artifact_to_dict

from llm_engines.contracts import (
    ChatMessage,
    EngineCapabilities,
    GenerationResponse,
    ToolCall,
    UsageStats,
)
from llm_engines.tool_process_probe import (
    TOOL_PROCESS_PROFILE,
    build_tool_decision_artifact,
    run_tool_decision_campaign,
)


class ToolDecisionEngine:
    BACKEND = "synthetic"
    model = "synthetic-model"

    def get_capabilities(self):
        return EngineCapabilities(tool_calling=True)

    def generate(self, request):
        raise AssertionError("ordinary generation is not used")

    def generate_with_tools(self, request, available_tools):
        prompt = request.messages[-1].content or ""
        if "REC-17" in prompt:
            calls = [
                ToolCall(
                    call_id="one",
                    name="lookup_record",
                    arguments={"code": "REC-17"},
                )
            ]
            text = None
        elif "add 4 and 9" in prompt:
            calls = [
                ToolCall(
                    call_id="two",
                    name="add_numbers",
                    arguments={"left": 4, "right": 9},
                )
            ]
            text = None
        elif "BLUE" in prompt:
            calls = []
            text = "BLUE"
        else:
            calls = [
                ToolCall(
                    call_id="three",
                    name="set_flag",
                    arguments={"enabled": True, "count": 3},
                )
            ]
            text = None
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=text, tool_calls=calls),
            finish_reason="tool_call" if calls else "stop",
            usage=UsageStats(latency_ms=4.0),
            model_name=self.model,
            backend=self.BACKEND,
        )


def test_tool_decision_campaign_passes_all_fixed_cases_and_aggregates():
    report = run_tool_decision_campaign(ToolDecisionEngine(), repetitions=2)

    assert report.repetitions == 2
    assert report.cases_per_run == 4
    assert report.profile_version == 2
    assert report.thinking_requested is None
    assert len(report.results) == 8
    assert all(result.status == "passed" for result in report.results)
    assert report.case_aggregates["choose_relevant_tool"]["pass_rate"] == 1.0
    assert report.case_aggregates["avoid_unnecessary_tool"]["latency_ms"] == {
        "samples": 2,
        "minimum": 4.0,
        "median": 4.0,
        "maximum": 4.0,
    }


def test_tool_decision_campaign_detects_wrong_arguments_without_retaining_them():
    class WrongArgumentsEngine(ToolDecisionEngine):
        def generate_with_tools(self, request, available_tools):
            response = super().generate_with_tools(request, available_tools)
            if "REC-17" not in (request.messages[-1].content or ""):
                return response
            return response.model_copy(
                update={
                    "message": ChatMessage(
                        role="assistant",
                        tool_calls=[
                            ToolCall(
                                call_id="wrong",
                                name="lookup_record",
                                arguments={"code": "PRIVATE-WRONG-VALUE"},
                            )
                        ],
                    )
                }
            )

    report = run_tool_decision_campaign(WrongArgumentsEngine(), repetitions=1)
    result = next(item for item in report.results if item.case_id == "required_single_tool")

    assert result.status == "failed"
    assert result.arguments_match is False
    assert "PRIVATE-WRONG-VALUE" not in json.dumps(report.to_dict())


def test_tool_decision_campaign_retains_only_exception_type():
    class BrokenEngine(ToolDecisionEngine):
        def generate_with_tools(self, request, available_tools):
            raise RuntimeError("private provider detail")

    report = run_tool_decision_campaign(BrokenEngine(), repetitions=1)

    assert all(result.status == "error" for result in report.results)
    assert all(result.error_type == "RuntimeError" for result in report.results)
    assert "private provider detail" not in json.dumps(report.to_dict())


def test_tool_decision_campaign_rejects_unsupported_engine():
    from llm_engines.backends.mock import MockEngine

    with pytest.raises(ValueError, match="tool calling"):
        run_tool_decision_campaign(MockEngine())


def test_tool_decision_artifact_round_trips_with_validated_privacy():
    report = run_tool_decision_campaign(ToolDecisionEngine(), repetitions=1)
    artifact = artifact_from_dict(
        artifact_to_dict(build_tool_decision_artifact(report))
    )

    assert artifact.envelope.profile == TOOL_PROCESS_PROFILE
    assert artifact.envelope.profile_version == 2
    assert artifact.envelope.privacy.validation.status == "validated"
    assert artifact.body["case_aggregates"]["typed_arguments"]["passed"] == 1
    assert "Use lookup_record" not in json.dumps(artifact.body)


def test_tool_decision_campaign_sanitizes_absolute_model_path():
    engine = ToolDecisionEngine()
    engine.model = "/home/private/models/synthetic.gguf"

    report = run_tool_decision_campaign(engine, repetitions=1, thinking=False)

    assert report.model_label == "synthetic.gguf"
    assert report.thinking_requested is False
    assert "/home/private" not in json.dumps(report.to_dict())
