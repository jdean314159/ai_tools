from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from llm_harness_core import artifact_from_dict, artifact_to_dict

from llm_engines.contracts import (
    ChatMessage,
    EngineCapabilities,
    GenerationResponse,
    ToolCall,
    UsageStats,
)
from llm_engines.tool_recovery_probe import (
    TOOL_RECOVERY_DEVELOPMENT_PROFILE,
    TOOL_RECOVERY_PROFILE,
    build_tool_recovery_artifact,
    require_baseline_headroom,
    run_tool_recovery_development,
    run_tool_recovery_pilot,
)


def _response(*, text=None, tool=None, arguments=None, seed_status="not_requested"):
    calls = []
    if tool:
        calls = [ToolCall(call_id="call-1", name=tool, arguments=arguments or {})]
    return GenerationResponse(
        message=ChatMessage(role="assistant", content=text, tool_calls=calls),
        finish_reason="tool_call" if calls else "stop",
        usage=UsageStats(input_tokens=10, output_tokens=4, latency_ms=5.0),
        model_name="/private/models/synthetic.gguf",
        backend="synthetic",
        seed_status=seed_status,
    )


class RecoveryEngine:
    BACKEND = "synthetic"
    model = "/private/models/synthetic.gguf"

    def __init__(self, *, fail_contradiction=False, fabricate_retry=False):
        self.fail_contradiction = fail_contradiction
        self.fabricate_retry = fabricate_retry

    def get_capabilities(self):
        return EngineCapabilities(tool_calling=True)

    def generate(self, request):
        raise AssertionError("ordinary generation is not used")

    def generate_with_tools(self, request, available_tools):
        seed_status = "accepted" if request.seed is not None else "not_requested"
        latest = request.messages[-1].content or ""
        first = request.messages[0].content or ""
        if request.messages[-1].role == "user":
            if "R-17" in first:
                return _response(tool="lookup_record", arguments={"code": "R-17"}, seed_status=seed_status)
            if "R-23" in first:
                return _response(tool="lookup_record", arguments={"code": "R-23"}, seed_status=seed_status)
            if "R-31" in first:
                return _response(tool="lookup_record", arguments={"code": "R-31"}, seed_status=seed_status)
            return _response(tool="lookup_record", arguments={"code": "R-47"}, seed_status=seed_status)
        if "ERROR_TRANSIENT" in latest:
            if self.fabricate_retry:
                return _response(text="R-17 FOUND", seed_status=seed_status)
            return _response(tool="lookup_record", arguments={"code": "R-17"}, seed_status=seed_status)
        if "INACTIVE" in latest:
            return _response(
                tool="report_status",
                arguments={"status": "ACTIVE" if self.fail_contradiction else "INACTIVE"},
                seed_status=seed_status,
            )
        if "ERROR_UNAVAILABLE" in latest:
            return _response(tool="lookup_backup", arguments={"code": "R-31"}, seed_status=seed_status)
        return _response(tool="lookup_detail", arguments={"field": "region"}, seed_status=seed_status)


class DevelopmentEngine(RecoveryEngine):
    def generate_with_tools(self, request, available_tools):
        seed_status = "accepted" if request.seed is not None else "not_requested"
        first = request.messages[0].content or ""
        latest = request.messages[-1].content or ""
        if request.messages[-1].role == "user":
            initial = (
                ("D-101", "lookup_record", {"code": "D-101"}),
                ("D-211", "lookup_record", {"code": "D-211"}),
                ("D-301", "lookup_batch", {"codes": "D-301,D-302"}),
                ("D-407", "lookup_fields", {"code": "D-407"}),
                ("D-509", "secure_lookup", {"code": "D-509"}),
                ("D-613", "lookup_record", {"code": "D-613"}),
            )
            for marker, tool, arguments in initial:
                if marker in first:
                    return _response(tool=tool, arguments=arguments, seed_status=seed_status)
        recovery = (
            ("observed_at", "refresh_record", {"code": "D-101"}),
            ("checksum_unverified", "validate_record", {"code": "D-211"}),
            ("D-302=ERROR", "retry_record", {"code": "D-302"}),
            ("authority source=registry", "lookup_authority", {"source": "registry"}),
            ("ERROR_PERMISSION_DENIED", "request_human_review", {"code": "D-509"}),
            ("MALFORMED_RESULT", "strict_lookup", {"code": "D-613"}),
        )
        for marker, tool, arguments in recovery:
            if marker in latest:
                return _response(tool=tool, arguments=arguments, seed_status=seed_status)
        return _response(text="unexpected", seed_status=seed_status)


def test_perfect_baseline_is_ceiling_and_cannot_open_comparison_gate():
    report = run_tool_recovery_pilot(RecoveryEngine(), repetitions=2, seed=0)

    assert report.primary_pass_rate == 1.0
    assert report.baseline_headroom == "ceiling"
    assert report.model_label == "synthetic.gguf"
    assert all(result.seed_statuses == ("accepted", "accepted") for result in report.results)
    with pytest.raises(ValueError, match="ceiling"):
        require_baseline_headroom(report)


def test_v3_development_suite_is_separate_and_thinking_off():
    report = run_tool_recovery_development(DevelopmentEngine(), repetitions=1)

    assert report.profile == TOOL_RECOVERY_DEVELOPMENT_PROFILE
    assert report.profile_version == 1
    assert report.cases_per_run == 6
    assert report.thinking_requested is False
    assert report.seed_requested == 11
    assert report.primary_pass_rate == 1.0


def test_mixed_baseline_has_headroom():
    report = run_tool_recovery_pilot(
        RecoveryEngine(fail_contradiction=True), repetitions=1
    )

    assert report.primary_pass_rate == 0.75
    assert report.baseline_headroom == "present"
    require_baseline_headroom(report)


def test_fabricated_success_fails_even_after_valid_initial_call():
    report = run_tool_recovery_pilot(
        RecoveryEngine(fabricate_retry=True), repetitions=1
    )
    result = next(item for item in report.results if item.case_id == "transient_retry")

    assert result.status == "failed"
    assert result.fabricated_success is True
    assert report.fabricated_success_rate == 0.25


def test_artifact_is_privacy_bounded_and_seed_does_not_claim_determinism():
    report = run_tool_recovery_pilot(RecoveryEngine(), repetitions=1, seed=7)
    artifact = artifact_from_dict(
        artifact_to_dict(build_tool_recovery_artifact(report))
    )
    encoded = json.dumps(artifact.body)

    assert artifact.envelope.profile == TOOL_RECOVERY_PROFILE
    assert artifact.envelope.profile_version == 2
    assert artifact.envelope.capabilities[0].determinism.claim == "best_effort"
    assert "seed requested and provider call accepted" in " ".join(
        artifact.envelope.capabilities[0].determinism.conditions
    )
    assert "ERROR_TRANSIENT" not in encoded
    assert "R-17 FOUND" not in encoded
    assert "/private" not in encoded


def test_non_tool_engine_is_rejected_before_running():
    from llm_engines.backends.mock import MockEngine

    with pytest.raises(ValueError, match="tool calling"):
        run_tool_recovery_pilot(MockEngine())


def test_committed_recovery_artifacts_match_pinned_bytes_and_privacy():
    repo = Path(__file__).resolve().parents[2]
    runs = repo / "docs" / "projects" / "llm_engines" / "runs"
    expected = {
        "2026-08-29-spark-qwen-tool-recovery-baseline-v1-invalid-scorer.json":
            "afbd321ad261a91bd5f1bc5abf87d08fa4fbfd0a3ccd227e1a0e69c183dc2a8e",
        "2026-08-29-spark-qwen-tool-recovery-baseline-v2.json":
            "9c2405cc7903b1b4c52a807851d3ab316f7645b229965bb04ce2c57818315009",
    }
    forbidden = ("192.168.50.225", "/home/", "cybernaif", "ERROR_TRANSIENT", "R-23")

    for name, digest in expected.items():
        content = (runs / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        decoded = content.decode("utf-8")
        assert not any(value in decoded for value in forbidden)
