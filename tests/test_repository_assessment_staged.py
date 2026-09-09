from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from llm_engines.contracts import ChatMessage, GenerationResponse, ToolCall, UsageStats


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/projects/repository_assessment/tools/run_staged_assessment.py"
)
SPEC = importlib.util.spec_from_file_location("run_staged_assessment", SCRIPT_PATH)
assert SPEC is not None
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _response(tool: str, arguments: dict) -> GenerationResponse:
    return GenerationResponse(
        message=ChatMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(call_id="call-1", name=tool, arguments=arguments)],
        ),
        finish_reason="tool_call",
        usage=UsageStats(input_tokens=10, output_tokens=4, total_tokens=14, latency_ms=1.0),
        model_name="fixture",
        backend="fixture",
        seed_status="accepted",
    )


def _no_candidate() -> GenerationResponse:
    return _response(
        "submit_scope_report",
        {
            "disposition": "no_candidate",
            "severity": "none",
            "expected_behavior": "The inspected contract should hold.",
            "suspected_violation": "No surviving violation.",
            "symbols": "None.",
            "evidence": "The inspected paths were consistent.",
            "disconfirmation_attempt": "Searched callers and guards.",
        },
    )


class FakeEngine:
    def __init__(self) -> None:
        self.responses = [_no_candidate() for _ in runner.PACKAGE_NAMES]
        self.responses.append(
            _response("submit_synthesis", {"report": "# Assessment\n\nNo accepted findings."})
        )

    def generate_with_tools(self, request, available_tools):
        del request, available_tools
        return self.responses.pop(0)

    def generate(self, request):  # pragma: no cover - no confirmed fixture candidates
        raise AssertionError(f"unexpected critic request: {request}")


def _fingerprint() -> dict:
    return {
        "launch_configuration": {},
        "llama_build": "fixture",
        "model_metadata": {"model_label": "fixture"},
        "model_sha256": None,
        "omissions": ["fixture"],
    }


def test_sanitized_sandbox_overlays_historical_docs_after_target_mount(tmp_path: Path) -> None:
    argv = runner.sanitized_sandbox_argv(
        tmp_path / "target", tmp_path / "venv", tmp_path / "rg", "true"
    )
    target_mount = argv.index("/workspace")
    internal_mask = argv.index("/workspace/docs/internal")
    projects_mask = argv.index("/workspace/docs/projects")

    assert target_mount < internal_mask < projects_mask
    assert argv[internal_mask - 1] == "--tmpfs"
    assert argv[projects_mask - 1] == "--tmpfs"


def test_relative_path_normalization_supports_assigned_scope() -> None:
    command = "cd /workspace/engram && sed -n '1,80p' src/engram/project_memory.py; cat README.md"
    paths = runner.normalized_command_paths(command, "engram")

    assert "/workspace/engram/src/engram/project_memory.py" in paths
    assert "/workspace/engram/README.md" in paths


def test_candidate_selection_uses_order_and_six_candidate_limit() -> None:
    items = [{"scope": f"scope-{index}", "disposition": "candidate"} for index in range(8)]
    items.insert(2, {"scope": "empty", "disposition": "no_candidate"})

    selected = runner.select_candidates(items)

    assert len(selected) == 6
    assert [item["scope"] for item in selected] == [
        "scope-0",
        "scope-1",
        "scope-2",
        "scope-3",
        "scope-4",
        "scope-5",
    ]


def test_controller_uncertainty_comes_only_from_coverage() -> None:
    assert runner.controller_uncertainty(7) == "high"
    assert runner.controller_uncertainty(8) == "medium"
    assert runner.controller_uncertainty(9) == "low"


def test_target_identity_override_requires_and_retains_all_three_fields() -> None:
    identity = {
        "target_commit": "1" * 40,
        "target_tree": "2" * 40,
        "target_archive_sha256": "3" * 64,
    }

    assert runner.normalize_target_identity(identity) == identity

    try:
        runner.normalize_target_identity({"target_commit": "1" * 40})
    except ValueError as error:
        assert "exactly" in str(error)
    else:  # pragma: no cover - contract guard
        raise AssertionError("partial target identity must fail")


def test_staged_run_with_no_candidates_completes_structured(tmp_path: Path) -> None:
    identity = {
        "target_commit": "1" * 40,
        "target_tree": "2" * 40,
        "target_archive_sha256": "3" * 64,
    }
    metadata = runner.run_staged_assessment(
        engine=FakeEngine(),
        seed=17,
        root=tmp_path,
        venv=tmp_path,
        rg_path=tmp_path / "rg",
        output_dir=tmp_path / "run",
        fingerprint=_fingerprint(),
        environment_validation={"valid": True},
        target_identity=identity,
    )

    assert metadata["completion_mode"] == "structured"
    assert metadata["scouts"]["structured"] == 9
    assert metadata["candidate_selection"]["selected"] == 0
    assert metadata["shell_tool_calls"] == 0
    assert metadata["remaining_uncertainty"] == "high"
    assert metadata["accepted_findings"] == []
    assert {key: metadata[key] for key in identity} == identity
