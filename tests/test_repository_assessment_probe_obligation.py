from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/projects/repository_assessment/tools/run_probe_obligation_screen.py"
)
SPEC = importlib.util.spec_from_file_location("run_probe_obligation_screen", SCRIPT_PATH)
assert SPEC is not None
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _state_with_probe(*, satisfied: bool = True) -> object:
    state = runner.ScreenState()
    state.probe_records.append(
        {
            "probe_call_id": "probe-123",
            "satisfied": satisfied,
            "stdout": "observed value: 42\n",
            "stderr": "",
            "workspace_module_files": ["/workspace/example/src/example/__init__.py"],
        }
    )
    return state


def _report_arguments(*, probe_call_id: str, observation: str) -> dict[str, str]:
    report = "# Validated Findings\n\nNone.\n"
    if probe_call_id != "none":
        report += f"\n# Behavioral probe\n\n{probe_call_id}: {observation}\n"
    return {
        "report": report,
        "disposition": "no_findings",
        "remaining_uncertainty": "high",
        "probe_call_id": probe_call_id,
        "probe_observation": observation,
    }


def test_treatment_only_model_visible_text_is_oracle_generic() -> None:
    assert runner.treatment_language_violations() == []


def test_both_conditions_expose_identical_tool_schemas() -> None:
    digests = {
        name: runner.tool_schema_sha256(tool)
        for name, tool in {
            "shell": runner.base.SHELL_TOOL,
            "run_probe": runner.RUN_PROBE_TOOL,
            "submit_report": runner.SCREEN_REPORT_TOOL,
        }.items()
    }

    assert len(set(digests.values())) == 3
    assert runner.controller_policy()["control_submission_requires_probe"] is False
    assert runner.controller_policy()["treatment_submission_requires_probe"] is True


def test_probe_mount_is_private_tmp_and_historical_docs_are_masked(tmp_path: Path) -> None:
    argv = runner._probe_sandbox_argv(
        tmp_path / "target",
        tmp_path / "venv",
        tmp_path / "rg",
        tmp_path / "scratch",
        "probe.py",
    )

    target_mount = argv.index("/workspace")
    internal_mask = argv.index("/workspace/docs/internal")
    projects_mask = argv.index("/workspace/docs/projects")
    probe_mount = argv.index("/tmp/model_probe")
    assert target_mount < internal_mask < projects_mask < probe_mount
    assert argv[probe_mount - 2] == "--ro-bind"
    assert "--unshare-all" in argv


def test_negative_control_rejects_nominal_probe_without_workspace_import() -> None:
    arguments = _report_arguments(probe_call_id="probe-123", observation="observed value: 42")

    parsed, reason = runner.validate_submission(
        arguments,
        condition="probe_required",
        state=_state_with_probe(satisfied=False),
    )

    assert parsed is None
    assert reason == "probe_call_id does not identify one satisfying in-run probe"


def test_treatment_rejects_no_probe_while_control_accepts_it() -> None:
    arguments = _report_arguments(probe_call_id="none", observation="none")

    control, control_reason = runner.validate_submission(
        arguments,
        condition="probe_optional",
        state=runner.ScreenState(),
    )
    treatment, treatment_reason = runner.validate_submission(
        arguments,
        condition="probe_required",
        state=runner.ScreenState(),
    )

    assert control is not None
    assert control_reason == "accepted"
    assert treatment is None
    assert "required instrumented behavioral probe" in treatment_reason


def test_satisfying_probe_requires_exact_report_reference() -> None:
    state = _state_with_probe()
    arguments = _report_arguments(probe_call_id="probe-123", observation="observed value: 42")

    parsed, reason = runner.validate_submission(
        arguments,
        condition="probe_required",
        state=state,
    )

    assert parsed is not None
    assert reason == "accepted"
    arguments["probe_observation"] = "invented value: 99"
    rejected, reason = runner.validate_submission(
        arguments,
        condition="probe_required",
        state=state,
    )
    assert rejected is None
    assert reason == "probe observation is not an exact retained output excerpt"


def test_structural_noncompletion_is_distinct_from_zero_recall() -> None:
    policy = runner.controller_policy()

    assert policy["forced_without_satisfying_probe"] == "structural_noncompletion"
    assert "recall" not in policy["forced_without_satisfying_probe"]


def test_completed_treatment_run_requires_satisfying_probe(tmp_path: Path, monkeypatch) -> None:
    report = (
        "# Validated Findings\n\nNone.\n\n# Behavioral probe\n\nprobe-123: observed value: 42\n"
    )

    class FakeEngine:
        def generate_with_tools(self, request, available_tools):
            del request, available_tools
            from llm_engines.contracts import (
                ChatMessage,
                GenerationResponse,
                ToolCall,
                UsageStats,
            )

            return GenerationResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[
                        ToolCall(
                            call_id="submit-1",
                            name="submit_report",
                            arguments={
                                "report": report,
                                "disposition": "no_findings",
                                "remaining_uncertainty": "high",
                                "probe_call_id": "probe-123",
                                "probe_observation": "observed value: 42",
                            },
                        )
                    ],
                ),
                finish_reason="tool_call",
                usage=UsageStats(
                    input_tokens=10,
                    output_tokens=4,
                    total_tokens=14,
                    latency_ms=1.0,
                ),
                model_name="fixture",
                backend="fixture",
                seed_status="accepted",
            )

    state_probe = {
        "probe_call_id": "probe-123",
        "satisfied": True,
        "stdout": "observed value: 42\n",
        "stderr": "",
        "workspace_module_files": ["/workspace/example/src/example/__init__.py"],
    }
    original_state = runner.ScreenState

    class PrimedState(original_state):
        def __init__(self):
            super().__init__()
            self.probe_records.append(state_probe)

    monkeypatch.setattr(runner, "ScreenState", PrimedState)
    fingerprint = {
        "launch_configuration": {},
        "llama_build": "fixture",
        "model_metadata": {"model_label": runner.MODEL_LABEL},
        "model_sha256": None,
        "omissions": ["fixture"],
    }
    metadata = runner.run_screen(
        engine=FakeEngine(),
        condition="probe_required",
        seed=runner.SEED,
        root=tmp_path,
        venv=tmp_path,
        rg_path=tmp_path / "rg",
        output_dir=tmp_path / "run",
        fingerprint=fingerprint,
        environment_validation={"valid": True},
    )

    assert metadata["completion_mode"] == "natural"
    assert metadata["satisfying_probe_calls"] == 1
    assert metadata["report_probe_call_id"] == "probe-123"
    stored = json.loads((tmp_path / "run/run-metadata.json").read_text(encoding="utf-8"))
    assert stored["outcome"] == "natural_valid_submission"
