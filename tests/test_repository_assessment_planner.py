from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from llm_engines.contracts import ChatMessage, GenerationResponse, ToolCall, UsageStats


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/projects/repository_assessment/tools/run_planner_assessment.py"
)
SPEC = importlib.util.spec_from_file_location("run_planner_assessment", SCRIPT_PATH)
assert SPEC is not None
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _result() -> dict:
    return {"returncode": 0, "stdout": "content", "stdout_length": 7}


def _response(*, tool: str, arguments: dict, text: str = "") -> GenerationResponse:
    return GenerationResponse(
        message=ChatMessage(
            role="assistant",
            content=text,
            tool_calls=[ToolCall(call_id="call-1", name=tool, arguments=arguments)],
        ),
        finish_reason="tool_call",
        usage=UsageStats(input_tokens=10, output_tokens=4, total_tokens=14, latency_ms=1.0),
        model_name="fixture",
        backend="fixture",
        seed_status="accepted",
    )


class FakeEngine:
    def __init__(self, tool_responses: list[GenerationResponse], critic_response: str = "") -> None:
        self.tool_responses = list(tool_responses)
        self.critic_response = critic_response

    def generate_with_tools(self, request, available_tools):
        del request, available_tools
        return self.tool_responses.pop(0)

    def generate(self, request):
        del request
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=self.critic_response),
            finish_reason="stop",
            usage=UsageStats(input_tokens=7, output_tokens=3, total_tokens=10, latency_ms=1.0),
            model_name="fixture",
            backend="fixture",
            seed_status="accepted",
        )


def _fingerprint() -> dict:
    return {
        "launch_configuration": {},
        "llama_build": "fixture",
        "model_metadata": {"model_label": "fixture"},
        "model_sha256": None,
        "omissions": ["fixture"],
    }


def test_coverage_ledger_requires_source_and_corroborating_read() -> None:
    ledger = runner.CoverageLedger(seed=17)
    scope = ledger.current_scope
    assert scope is not None
    production = (
        f"/workspace/{scope}/module.py"
        if scope == "mail_lib"
        else f"/workspace/{scope}/src/{scope}/module.py"
    )

    assert ledger.observe(f"sed -n '1,80p' {production}", _result()) is False
    assert ledger.covered_count == 0
    assert ledger.observe(f"cat /workspace/{scope}/README.md", _result()) is True
    assert ledger.covered_count == 1
    assert ledger.current_scope != scope


def test_coverage_ledger_advances_after_five_calls_and_marks_exhausted() -> None:
    ledger = runner.CoverageLedger(seed=31)
    scope = ledger.current_scope
    assert scope is not None

    for index in range(4):
        assert ledger.observe(f"cat /workspace/{scope}/README.md # {index}", _result()) is False
    assert ledger.observe(f"cat /workspace/{scope}/README.md # final", _result()) is True
    assert ledger.scopes[scope].exhausted is True
    assert ledger.scopes[scope].covered is False


def test_planner_scope_order_is_seeded_and_commands_are_confined() -> None:
    first = runner.CoverageLedger(seed=47)
    second = runner.CoverageLedger(seed=47)
    assert first.order == second.order
    assert set(first.order) == set(runner.PACKAGE_NAMES)
    assert first.command_matches_current_scope(f"cat /workspace/{first.current_scope}/README.md")
    assert not first.command_matches_current_scope("cat /workspace/README.md")


def test_validated_finding_extraction_handles_none_and_multiple() -> None:
    assert runner.extract_validated_findings("# Validated Findings\n\nNone.\n") == []
    report = """# Validated Findings

## First

Evidence one.

## Second

Evidence two.

# Remaining Uncertainty

Medium.
"""
    findings = runner.extract_validated_findings(report)
    assert len(findings) == 2
    assert findings[0].startswith("## First")
    assert findings[1].startswith("## Second")

    singular = """## Validated Finding

**Severity**: High

Evidence.

## Remaining Uncertainty

Low.
"""
    assert runner.extract_validated_findings(singular) == ["**Severity**: High\n\nEvidence."]

    key_findings_none = """## Key Findings

None validated - command restrictions prevented further inspection.

## Remaining Uncertainty

High.
"""
    assert runner.extract_validated_findings(key_findings_none) == []
    assert runner.extract_validated_findings("No validated defects were found.") == []
    assert runner.extract_validated_findings("A malformed report asserting a defect.") == [
        "A malformed report asserting a defect."
    ]


def test_passive_coverage_records_baseline_source_and_contract() -> None:
    scopes = {name: runner.ScopeEvidence() for name in runner.PACKAGE_NAMES}
    runner.observe_passive_coverage(
        scopes,
        "cat /workspace/engram/src/engram/trust.py",
        _result(),
    )
    runner.observe_passive_coverage(scopes, "cat /workspace/engram/README.md", _result())

    snapshot = runner.passive_coverage_snapshot(scopes)
    assert snapshot["covered"] == 1
    assert snapshot["scopes"]["engram"]["covered"] is True


def test_baseline_natural_report_records_structured_uncertainty(tmp_path: Path) -> None:
    report = "# Validated Findings\n\nNone."
    engine = FakeEngine(
        [
            _response(
                tool="submit_report", arguments={"report": report, "remaining_uncertainty": "high"}
            )
        ]
    )
    output = tmp_path / "baseline"

    metadata = runner.run_assessment(
        engine=engine,
        condition="baseline",
        seed=17,
        root=tmp_path,
        venv=tmp_path,
        rg_path=tmp_path / "rg",
        output_dir=output,
        fingerprint=_fingerprint(),
        environment_validation={"valid": True},
    )

    assert metadata["completion_mode"] == "natural"
    assert metadata["remaining_uncertainty"] == "high"
    assert metadata["critic"]["calls"] == 0
    assert (output / "raw-model-report.md").read_text(encoding="utf-8").endswith("\n")


def test_planner_rejects_low_uncertainty_before_eight_scopes(tmp_path: Path) -> None:
    report = "# Validated Findings\n\nNone."
    engine = FakeEngine(
        [
            _response(
                tool="submit_report",
                arguments={"report": report, "remaining_uncertainty": "low"},
            ),
            _response(
                tool="submit_report",
                arguments={"report": report, "remaining_uncertainty": "medium"},
            ),
        ]
    )

    metadata = runner.run_assessment(
        engine=engine,
        condition="planner",
        seed=31,
        root=tmp_path,
        venv=tmp_path,
        rg_path=tmp_path / "rg",
        output_dir=tmp_path / "planner",
        fingerprint=_fingerprint(),
        environment_validation={"valid": True},
    )

    assert metadata["completion_mode"] == "natural"
    assert metadata["remaining_uncertainty"] == "medium"
    assert metadata["rejected_tool_calls"] == 1


def test_planner_critic_accepts_a_proposed_finding(tmp_path: Path) -> None:
    report = "# Validated Findings\n\n## Defect\n\nThe evidence demonstrates a defect."
    engine = FakeEngine(
        [
            _response(
                tool="submit_report",
                arguments={"report": report, "remaining_uncertainty": "high"},
            )
        ],
        critic_response=json.dumps({"decision": "accept", "rationale": "Evidence is direct."}),
    )

    metadata = runner.run_assessment(
        engine=engine,
        condition="planner",
        seed=47,
        root=tmp_path,
        venv=tmp_path,
        rg_path=tmp_path / "rg",
        output_dir=tmp_path / "critic",
        fingerprint=_fingerprint(),
        environment_validation={"valid": True},
    )

    assert metadata["completion_mode"] == "natural"
    assert metadata["critic"]["calls"] == 1
    assert metadata["critic"]["records"][0]["decision"] == "accept"


def test_sandbox_argv_unshares_and_mounts_target_read_only(tmp_path: Path) -> None:
    argv = runner.sandbox_argv(tmp_path / "target", tmp_path / "venv", tmp_path / "rg", "true")
    assert "--unshare-all" in argv
    assert "--tmpfs" in argv
    root_index = argv.index(str(tmp_path / "target"))
    assert argv[root_index - 1] == "--ro-bind"
    assert argv[root_index + 1] == "/workspace"
