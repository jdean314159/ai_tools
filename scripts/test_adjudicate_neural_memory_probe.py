from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("adjudicate_neural_memory_probe.py")
SPEC = importlib.util.spec_from_file_location(
    "adjudicate_neural_memory_probe",
    SCRIPT_PATH,
)
assert SPEC is not None
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def _case() -> dict:
    return {
        "case_id": "neural-memory-arc",
        "focal_candidate_ids": [
            "candidate-e5b8ff4a96914696",
            "candidate-1daddd4ca13cf45a",
            "candidate-fa30e8c2f2f35393",
            "candidate-738380e8de4da93d",
        ],
        "historical_claims": [
            {
                "claim_id": "hypothesis-neural-affinity-improves-retrieval",
            }
        ],
        "evidence": [
            {
                "evidence_id": "eval",
                "authority": "local_evaluation",
                "statement": "Evaluation failed.",
            },
            {
                "evidence_id": "adr",
                "authority": "accepted_adr",
                "statement": "Feature parked.",
            },
        ],
        "expected": {
            "hypothesis-neural-affinity-improves-retrieval": "resolved_against",
            "candidate-e5b8ff4a96914696": "qualified",
            "candidate-1daddd4ca13cf45a": "qualified",
            "candidate-fa30e8c2f2f35393": "unresolved",
            "candidate-738380e8de4da93d": "unresolved",
        },
        "expected_review_required": {
            "candidate-738380e8de4da93d": True,
        },
    }


def _result() -> probe.ProbeResult:
    statuses = _case()["expected"]
    return probe.ProbeResult(
        relations=[
            probe.ProposedRelation(
                candidate_id="candidate-e5b8ff4a96914696",
                evidence_id="eval",
                relation="challenges",
                rationale="The local evaluation found no benefit.",
            ),
            probe.ProposedRelation(
                candidate_id="candidate-e5b8ff4a96914696",
                evidence_id="adr",
                relation="supersedes",
                rationale="The accepted ADR parks the integration.",
            ),
            probe.ProposedRelation(
                candidate_id="candidate-fa30e8c2f2f35393",
                evidence_id="eval",
                relation="unresolved",
                rationale="The retrieval evaluation did not measure storage reduction.",
            ),
        ],
        adjudications=[
            probe.ProposedAdjudication(
                candidate_id=candidate_id,
                status=status,
                current_statement=("Current statement preserving historical context and scope."),
                rationale="Evidence was evaluated according to authority and scope.",
                controlling_evidence_ids=(["eval", "adr"] if status == "resolved_against" else []),
                review_required=status in {"unresolved", "qualified"},
            )
            for candidate_id, status in statuses.items()
        ],
        current_guidance=(
            "Neural re-ranking is disabled; the layer is parked and default-off. "
            "Reactivation requires a new need and predeclared gate."
        ),
    )


def test_valid_probe_passes() -> None:
    graph = probe.validate_result(_result(), _case())

    assert graph["status"] == "pass"
    assert graph["errors"] == []
    assert all(item["historical_claim_preserved"] for item in graph["claims"])


def test_architecture_description_cannot_be_resolved_against() -> None:
    result = _result()
    titans = next(
        item for item in result.adjudications if item.candidate_id == "candidate-1daddd4ca13cf45a"
    )
    titans.status = "resolved_against"
    titans.controlling_evidence_ids = ["eval"]

    graph = probe.validate_result(result, _case())

    assert graph["status"] == "fail"
    assert any("incorrectly resolved against" in error for error in graph["errors"])


def test_resolved_against_requires_strong_controlling_evidence() -> None:
    case = _case()
    case["evidence"][0]["authority"] = "conversation_assessment"
    case["evidence"][1]["authority"] = "source_summary"
    result = _result()

    graph = probe.validate_result(result, case)

    assert graph["status"] == "fail"
    assert any("without controlling evidence" in error for error in graph["errors"])


def test_guidance_requires_operational_resolution() -> None:
    result = _result()
    result.current_guidance = "The feature requires additional study before use."

    graph = probe.validate_result(result, _case())

    assert graph["status"] == "fail"
    assert any("current guidance missing" in error for error in graph["errors"])


def test_synthesis_claim_requires_human_review() -> None:
    result = _result()
    synthesis = next(
        item for item in result.adjudications if item.candidate_id == "candidate-738380e8de4da93d"
    )
    synthesis.review_required = False

    graph = probe.validate_result(result, _case())

    assert graph["status"] == "fail"
    assert any("expected review_required=True" in error for error in graph["errors"])
