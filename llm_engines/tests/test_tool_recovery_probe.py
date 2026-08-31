from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

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
    run_tool_recovery_development_v4,
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


class MultiVariantDevelopmentEngine(RecoveryEngine):
    def __init__(self, *, fail_variant_five=False):
        self.fail_variant_five = fail_variant_five

    def generate_with_tools(self, request, available_tools):
        seed_status = "accepted" if request.seed is not None else "not_requested"
        first = request.messages[0].content or ""
        latest = request.messages[-1].content or ""
        code = re.search(r"V4-[A-Z]\d{3}", first)
        assert code is not None
        code_value = code.group(0)
        if request.messages[-1].role == "user":
            names = {tool.name for tool in available_tools}
            if "lookup_batch" in names:
                codes = re.search(r"V4-B\d{3},V4-B\d{3}", first)
                assert codes is not None
                return _response(tool="lookup_batch", arguments={"codes": codes.group(0)}, seed_status=seed_status)
            initial = "lookup_fields" if "lookup_fields" in names else "secure_lookup" if "secure_lookup" in names else "lookup_record"
            return _response(tool=initial, arguments={"code": code_value}, seed_status=seed_status)

        fifth_variant_codes = {"V4-S105", "V4-W205", "V4-B341", "V4-A405", "V4-P505", "V4-M605"}
        if self.fail_variant_five and code_value in fifth_variant_codes:
            return _response(text="unable to recover", seed_status=seed_status)
        if "ERROR_TRANSIENT" in latest:
            failed = re.search(r"(V4-B\d{3})=ERROR_TRANSIENT", latest)
            assert failed is not None
            return _response(tool="retry_record", arguments={"code": failed.group(1)}, seed_status=seed_status)
        if "governing source=" in latest:
            source = re.search(r"governing source=([a-z_]+)", latest)
            assert source is not None
            return _response(tool="lookup_authority", arguments={"source": source.group(1)}, seed_status=seed_status)
        recovery_tool = (
            "refresh_record" if "SUCCESS: status=OPEN" in latest
            else "validate_record" if "WARNING:" in latest
            else "request_human_review" if "ERROR_PERMISSION_DENIED" in latest
            else "strict_lookup"
        )
        return _response(tool=recovery_tool, arguments={"code": code_value}, seed_status=seed_status)


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


def test_v4_development_measures_five_distinct_variants_per_family():
    report = run_tool_recovery_development_v4(MultiVariantDevelopmentEngine())

    assert report.campaign.profile == TOOL_RECOVERY_DEVELOPMENT_PROFILE
    assert report.campaign.profile_version == 2
    assert report.campaign.repetitions == 1
    assert report.campaign.cases_per_run == 30
    assert report.campaign.thinking_requested is False
    assert report.campaign.seed_requested == 17
    assert len({result.case_id for result in report.campaign.results}) == 30
    assert {result.distinct_variants for result in report.family_results} == {5}
    assert report.eligible_family_count == 0
    assert report.advancement_ready is False


def test_v4_eligibility_uses_cross_variant_outcomes():
    report = run_tool_recovery_development_v4(
        MultiVariantDevelopmentEngine(fail_variant_five=True)
    )

    assert {result.passed_variants for result in report.family_results} == {4}
    assert {result.pass_rate for result in report.family_results} == {0.8}
    assert all(result.evaluation_eligible for result in report.family_results)
    assert report.eligible_family_count == 6
    assert report.advancement_ready is True


def test_v4_artifact_retains_aggregate_variant_results_not_raw_cases():
    report = run_tool_recovery_development_v4(MultiVariantDevelopmentEngine())
    artifact = artifact_from_dict(artifact_to_dict(build_tool_recovery_artifact(report)))
    encoded = json.dumps(artifact.body)

    assert artifact.envelope.profile == TOOL_RECOVERY_DEVELOPMENT_PROFILE
    assert artifact.envelope.profile_version == 2
    assert artifact.body["eligible_family_count"] == 0
    assert "V4-S101" not in encoded
    assert "current_at=" not in encoded


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
        "2026-08-31-spark-qwen38-flash-next-tool-recovery-baseline-v2.json":
            "1530cc7579d7b13e9059690178036594b497da9a333fd0dd5a4cf9c3a046c6a5",
        "2026-08-29-spark-qwen-tool-recovery-v3-development-v1.json":
            "8e8386f483c98856a406d8d95bbee304946220fe4fdee64839556941771293c8",
        "2026-08-30-spark-qwen-tool-recovery-v4-development-v1.json":
            "a304925a3db422887af26b9a1afb9ae97a45d4203e51a69319afbfc5d6dd23d8",
    }
    forbidden = (
        "192.168.50.225",
        "/home/",
        "cybernaif",
        "ERROR_TRANSIENT",
        "R-23",
        "V4-S101",
        "current_at=",
    )

    for name, digest in expected.items():
        content = (runs / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        decoded = content.decode("utf-8")
        assert not any(value in decoded for value in forbidden)
