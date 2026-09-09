from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from llm_engines.contracts import ChatMessage, GenerationResponse, ToolCall, UsageStats


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/projects/repository_assessment/tools/run_adaptive_staged_assessment.py"
)
SPEC = importlib.util.spec_from_file_location("run_adaptive_staged_assessment", SCRIPT_PATH)
assert SPEC is not None
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _response(*calls: ToolCall) -> GenerationResponse:
    return GenerationResponse(
        message=ChatMessage(role="assistant", content="", tool_calls=list(calls)),
        finish_reason="tool_call",
        usage=UsageStats(input_tokens=10, output_tokens=4, total_tokens=14, latency_ms=1.0),
        model_name="fixture",
        backend="fixture",
        seed_status="accepted",
    )


def _call(call_id: str, name: str, arguments: dict) -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments=arguments)


class FakeEngine:
    def __init__(self, responses: list[GenerationResponse]) -> None:
        self.responses = list(responses)

    def generate_with_tools(self, request, available_tools):
        del request, available_tools
        return self.responses.pop(0)

    def generate(self, request):  # pragma: no cover - stage fixture has no critic
        raise AssertionError(f"unexpected critic request: {request}")


class AdaptiveCampaignFakeEngine:
    def __init__(self) -> None:
        self.call_number = 0

    def generate_with_tools(self, request, available_tools):
        self.call_number += 1
        names = {tool.name for tool in available_tools}
        if names == {"select_hypothesis"}:
            dossier = json.loads(request.messages[1].content)
            selected = next(
                item for item in dossier["symbols"] if not item["path"].endswith("/__init__.py")
            )
            arguments = {
                "production_path": selected["path"],
                "symbol": selected["name"],
                "invariant": "Each accepted item is inserted once.",
                "expected_behavior_source": dossier["test_paths"][0],
                "disconfirmation_plan": "Compare the implementation with its test.",
            }
            return _response(_call(f"selection-{self.call_number}", "select_hypothesis", arguments))

        report_name = next(name for name in names if name != "shell")
        shell_messages = [
            message
            for message in request.messages
            if message.role == "tool" and message.name == "shell"
        ]
        if len(shell_messages) < 2:
            scope = json.loads(request.messages[1].content)["dossier_slice"]["scope"]
            command = (
                f"cat /workspace/{scope}/worker.py /workspace/{scope}/tests/test_worker.py"
                if scope == "mail_lib"
                else f"cat /workspace/{scope}/src/{scope}/worker.py "
                f"/workspace/{scope}/tests/test_worker.py"
            )
            return _response(_call(f"shell-{self.call_number}", "shell", {"command": command}))

        evidence = {
            "claim": "The implementation may insert an item twice.",
            "expected_behavior": "Each accepted item is inserted once.",
            "expected_behavior_source": json.loads(request.messages[1].content)["dossier_slice"][
                "selected_symbol"
            ]["expected_behavior_source"],
            "symbols": json.loads(request.messages[1].content)["dossier_slice"]["selected_symbol"][
                "symbol"
            ],
            "impact": "Potential duplicate writes.",
            "contract_call_id": json.loads(shell_messages[0].content)["evidence_id"],
            "contract_quote": "one insertion",
            "behavior_call_id": json.loads(shell_messages[1].content)["evidence_id"],
            "behavior_quote": "two insertions",
            "disconfirmation_call_id": json.loads(shell_messages[1].content)["evidence_id"],
            "disconfirmation_quote": "two insertions",
        }
        if report_name == "submit_hypothesis_result":
            evidence.update({"disposition": "unresolved"})
        else:
            evidence.update({"decision": "rejected", "remediation": "None."})
        return _response(_call(f"report-{self.call_number}", report_name, evidence))

    def generate(self, request):  # pragma: no cover - all verifier fixtures reject
        raise AssertionError(f"unexpected critic request: {request}")


def _dossier() -> dict:
    return {
        "schema": runner.DOSSIER_SCHEMA,
        "scope": "demo",
        "production_modules": ["demo/src/demo/api.py", "demo/src/demo/__init__.py"],
        "symbols": [
            {
                "path": "demo/src/demo/api.py",
                "name": "store_batch",
                "kind": "FunctionDef",
                "lineno": 3,
            }
        ],
        "exports": ["store_batch"],
        "test_paths": ["demo/tests/test_api.py"],
        "test_symbol_references": [
            {"test_path": "demo/tests/test_api.py", "symbol": "store_batch"}
        ],
        "readme_headings": ["# Demo"],
        "metadata_paths": ["demo/README.md", "demo/pyproject.toml"],
        "limits": {},
        "truncated": {},
    }


def _selection() -> dict[str, str]:
    return {
        "production_path": "demo/src/demo/api.py",
        "symbol": "store_batch",
        "invariant": "Batch storage inserts each accepted item once.",
        "expected_behavior_source": "demo/tests/test_api.py",
        "disconfirmation_plan": "Trace scalar and batch insertion counts.",
    }


def _result_arguments(decision_field: str, decision: str) -> dict[str, str]:
    return {
        decision_field: decision,
        "claim": "Batch storage inserts an accepted item twice.",
        "expected_behavior": "Each accepted item is inserted once.",
        "expected_behavior_source": "demo/tests/test_api.py",
        "symbols": "demo.api.store_batch",
        "impact": "Duplicate writes.",
        "contract_call_id": "shell-1",
        "contract_quote": "one insertion",
        "behavior_call_id": "shell-2",
        "behavior_quote": "two insertions",
        "disconfirmation_call_id": "shell-2",
        "disconfirmation_quote": "two insertions",
        **(
            {"remediation": "Remove the duplicate insertion."}
            if decision_field == "decision"
            else {}
        ),
    }


def test_package_dossier_is_deterministic_and_contains_symbols_and_test_refs(
    tmp_path: Path,
) -> None:
    package = tmp_path / "demo"
    (package / "src/demo").mkdir(parents=True)
    (package / "tests").mkdir()
    (package / "src/demo/api.py").write_text(
        "def store_batch(items):\n    return list(items)\n\n"
        "class Cache:\n    def _refresh(self):\n        return None\n",
        encoding="utf-8",
    )
    (package / "src/demo/__init__.py").write_text('__all__ = ["store_batch"]\n', encoding="utf-8")
    (package / "tests/test_api.py").write_text(
        "def test_store_batch():\n    assert store_batch([]) == []\n", encoding="utf-8"
    )
    (package / "README.md").write_text("# Demo\n\n## Contract\n", encoding="utf-8")
    (package / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    first = runner.build_package_dossier(tmp_path, "demo")
    second = runner.build_package_dossier(tmp_path, "demo")

    assert runner.canonical_dossier_bytes(first) == runner.canonical_dossier_bytes(second)
    assert runner.dossier_sha256(first) == runner.dossier_sha256(second)
    assert {item["name"] for item in first["symbols"]} == {
        "store_batch",
        "Cache",
        "Cache._refresh",
    }
    assert first["test_symbol_references"] == [
        {"test_path": "demo/tests/test_api.py", "symbol": "store_batch"}
    ]


def test_selection_requires_exact_non_initializer_symbol_and_known_contract() -> None:
    accepted, reason = runner.validate_selection(_selection(), _dossier())
    assert reason == "accepted"
    assert accepted == _selection()

    initializer = {**_selection(), "production_path": "demo/src/demo/__init__.py"}
    rejected, reason = runner.validate_selection(initializer, _dossier())
    assert rejected is None
    assert "__init__.py" in reason

    unknown_contract = {**_selection(), "expected_behavior_source": "docs/internal/STATUS.md"}
    rejected, reason = runner.validate_selection(unknown_contract, _dossier())
    assert rejected is None
    assert "absent" in reason


def test_evidence_quotes_must_resolve_within_the_same_stage() -> None:
    trace = runner.StageTrace(
        stage_id="scout:demo",
        scope="demo",
        calls=[
            {
                "evidence_id": "shell-1",
                "tool_call_id": "opaque-backend-1",
                "command": "cat test",
                "result": {"stdout": "contract says one insertion", "stderr": ""},
            },
            {
                "evidence_id": "shell-2",
                "tool_call_id": "opaque-backend-2",
                "command": "run repro",
                "result": {"stdout": "observed two insertions", "stderr": ""},
            },
        ],
    )
    arguments = _result_arguments("disposition", "supported")

    valid, errors = runner.validate_evidence_references(arguments, trace)
    assert valid is True
    assert errors == []

    invalid = {**arguments, "contract_call_id": "other-stage-call"}
    valid, errors = runner.validate_evidence_references(invalid, trace)
    assert valid is False
    assert "this stage" in errors[0]


def test_invalid_evidence_downgrades_supported_and_confirmed_results() -> None:
    trace = runner.StageTrace(stage_id="scout:demo", scope="demo", calls=[])
    scout = runner._validated_stage_result(
        arguments=_result_arguments("disposition", "supported"),
        result_kind="scout",
        selection=_selection(),
        trace=trace,
    )
    verifier = runner._validated_stage_result(
        arguments=_result_arguments("decision", "confirmed"),
        result_kind="verifier",
        selection=_selection(),
        trace=trace,
    )

    assert scout is not None
    assert scout["original_disposition"] == "supported"
    assert scout["disposition"] == "unresolved"
    assert verifier is not None
    assert verifier["original_decision"] == "confirmed"
    assert verifier["decision"] == "insufficient_evidence"


def test_controller_owns_selection_binding_and_retains_mismatched_report() -> None:
    arguments = {
        **_result_arguments("disposition", "supported"),
        "expected_behavior_source": "invariant_derived",
        "symbols": "a different symbol",
    }
    trace = runner.StageTrace(
        stage_id="scout:demo",
        scope="demo",
        calls=[
            {
                "evidence_id": "shell-1",
                "tool_call_id": "opaque-1",
                "command": "contract",
                "result": {"stdout": "one insertion", "stderr": ""},
            },
            {
                "evidence_id": "shell-2",
                "tool_call_id": "opaque-2",
                "command": "behavior",
                "result": {"stdout": "two insertions", "stderr": ""},
            },
        ],
    )

    result = runner._validated_stage_result(
        arguments=arguments,
        result_kind="scout",
        selection=_selection(),
        trace=trace,
    )

    assert result is not None
    assert result["reported_expected_behavior_source"] == "invariant_derived"
    assert result["expected_behavior_source"] == "demo/tests/test_api.py"
    assert result["reported_symbols"] == "a different symbol"
    assert result["symbols"] == "demo/src/demo/api.py::store_batch"
    assert result["selection_binding"]["valid"] is False
    assert result["original_disposition"] == "supported"
    assert result["disposition"] == "unresolved"


def test_invalid_negative_result_is_retained_without_positive_promotion() -> None:
    trace = runner.StageTrace(stage_id="scout:demo", scope="demo", calls=[])
    result = runner._validated_stage_result(
        arguments=_result_arguments("disposition", "disproved"),
        result_kind="scout",
        selection=_selection(),
        trace=trace,
    )

    assert result is not None
    assert result["evidence_validation"]["valid"] is False
    assert result["disposition"] == "disproved"
    assert "original_disposition" not in result


def test_promotion_prefers_supported_then_unresolved_in_seeded_order() -> None:
    order = ["a", "b", "c", "d", "e"]
    results = [
        {"scope": "a", "disposition": "unresolved"},
        {"scope": "b", "disposition": "disproved"},
        {"scope": "c", "disposition": "supported"},
        {"scope": "d", "disposition": "unresolved"},
        {"scope": "e", "disposition": "supported"},
    ]

    promoted = runner.promote_hypotheses(results, order)

    assert [item["scope"] for item in promoted] == ["c", "e", "a"]


def test_empirical_stage_enforces_shell_budget_and_retains_exact_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    shell_calls = [
        _call("opaque-backend-1", "shell", {"command": "contract"}),
        _call("opaque-backend-2", "shell", {"command": "behavior"}),
        _call("opaque-backend-3", "shell", {"command": "over budget"}),
    ]
    result = _result_arguments("disposition", "supported")
    engine = FakeEngine(
        [
            _response(*shell_calls),
            _response(_call("report-1", "submit_hypothesis_result", result)),
        ]
    )

    def fake_shell(root, venv, rg_path, command):
        del root, venv, rg_path
        stdout = "one insertion" if command == "contract" else "two insertions"
        return {
            "command": command,
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
            "stdout_length": len(stdout),
        }

    monkeypatch.setattr(runner.v1, "run_sanitized_shell", fake_shell)
    violations: list[str] = []
    total_calls = [0]
    usage = runner.v1.UsageTotal()
    transcript = tmp_path / "transcript.jsonl"

    record, natural, trace = runner.run_empirical_stage(
        engine=engine,
        seed=17,
        stage="scout",
        scope="demo",
        stage_id="scout:demo",
        system_prompt="system",
        user_payload={"selection": _selection()},
        selection=_selection(),
        report_tool=runner.HYPOTHESIS_RESULT_TOOL,
        shell_budget=2,
        root=tmp_path,
        venv=tmp_path,
        rg_path=tmp_path / "rg",
        transcript=transcript,
        usage=usage,
        total_shell_calls=total_calls,
        protocol_violations=violations,
    )

    assert natural is False
    assert record["disposition"] == "supported"
    assert record["evidence_validation"] == {"valid": True, "errors": []}
    assert total_calls == [2]
    assert len(trace.calls) == 2
    assert [item["evidence_id"] for item in trace.calls] == ["shell-1", "shell-2"]
    assert [item["tool_call_id"] for item in trace.calls] == [
        "opaque-backend-1",
        "opaque-backend-2",
    ]
    assert any("beyond budget" in item for item in violations)
    events = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    tool_events = [event for event in events if event["event"] == "tool"]
    assert [event["evidence_id"] for event in tool_events[:2]] == ["shell-1", "shell-2"]


def test_authoritative_report_contains_only_critic_accepted_findings() -> None:
    verification = {
        **_result_arguments("decision", "confirmed"),
        "scope": "demo",
    }
    report = runner.render_authoritative_report(
        accepted=[{"verification": verification}],
        verifications=[verification, {"scope": "other", "decision": "rejected", "claim": "No."}],
        coverage={"covered": 8, "scopes": {}},
        uncertainty="medium",
    )

    assert "Batch storage inserts an accepted item twice" in report
    assert "`other`: rejected" in report
    assert "Substantive package coverage: 8/9" in report


def test_complete_adaptive_campaign_obeys_budget_and_renders_without_model_synthesis(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "target"
    for scope in runner.PACKAGE_NAMES:
        package = root / scope
        source = package if scope == "mail_lib" else package / "src" / scope
        source.mkdir(parents=True)
        (package / "tests").mkdir()
        (source / "worker.py").write_text("def store(item):\n    return item\n", encoding="utf-8")
        (package / "tests/test_worker.py").write_text(
            "def test_store():\n    assert store('x') == 'x'\n", encoding="utf-8"
        )
        (package / "README.md").write_text("# Contract\n", encoding="utf-8")

    def fake_shell(root, venv, rg_path, command):
        del root, venv, rg_path
        stdout = "one insertion\ntwo insertions"
        return {
            "command": command,
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
            "stdout_length": len(stdout),
        }

    monkeypatch.setattr(runner.v1, "run_sanitized_shell", fake_shell)
    identity = {
        "target_commit": "1" * 40,
        "target_tree": "2" * 40,
        "target_archive_sha256": "3" * 64,
    }
    metadata = runner.run_adaptive_assessment(
        engine=AdaptiveCampaignFakeEngine(),
        seed=17,
        root=root,
        venv=tmp_path,
        rg_path=tmp_path / "rg",
        output_dir=tmp_path / "run",
        fingerprint={"model_metadata": {"model_label": "fixture"}},
        environment_validation={"valid": True},
        target_identity=identity,
    )

    assert metadata["completion_mode"] == "structured"
    assert metadata["condition"] == "adaptive_staged_v2_2"
    assert metadata["selections"]["valid"] == 9
    assert metadata["scouts"]["structured"] == 9
    assert metadata["promotion"]["selected"] == 3
    assert metadata["verifiers"]["structured"] == 3
    assert metadata["shell_tool_calls"] == 24
    assert metadata["shell_tool_calls"] <= metadata["budgets"]["shell_call_ceiling"]
    assert metadata["substantive_coverage"]["covered"] == 9
    assert metadata["accepted_findings"] == []
    assert metadata["authoritative_report"] == "deterministic_controller_renderer"
    assert {key: metadata[key] for key in identity} == identity
