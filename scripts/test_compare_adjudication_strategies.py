from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("compare_adjudication_strategies.py")
SPEC = importlib.util.spec_from_file_location(
    "compare_adjudication_strategies",
    SCRIPT_PATH,
)
assert SPEC is not None
comparison = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = comparison
SPEC.loader.exec_module(comparison)


def _case() -> dict:
    return {
        "case_id": "test",
        "historical_claims": [{"claim_id": "direct"}],
        "focal_candidate_ids": ["mixed", "numeric", "untested"],
        "evidence": [
            {
                "evidence_id": "eval",
                "authority": "local_evaluation",
                "statement": "Scoped evaluation failed.",
            },
            {
                "evidence_id": "adr",
                "authority": "accepted_adr",
                "statement": "Feature disabled.",
            },
        ],
        "expected": {
            "direct": "resolved_against",
            "mixed": "qualified",
            "numeric": "unresolved",
            "untested": "unresolved",
        },
        "expected_review_required": {"untested": True},
    }


def _policy() -> dict:
    return {
        "claims": {
            "direct": {
                "trait": "directly_refuted",
                "current_statement": "The directly tested claim failed its local evaluation.",
                "evidence_ids": ["eval", "adr"],
            },
            "mixed": {
                "trait": "mixed_scope",
                "current_statement": "The broad claim survives only with scoped qualification.",
                "evidence_ids": ["eval"],
            },
            "numeric": {
                "trait": "unsupported_numeric",
                "current_statement": "The numerical benefit is unsupported by supplied evidence.",
                "evidence_ids": [],
            },
            "untested": {
                "trait": "untested",
                "current_statement": "The distinct claim remains untested by supplied evidence.",
                "evidence_ids": [],
            },
        },
        "required_guidance_facts": [
            "Re-ranking is disabled.",
            "The feature is parked and default-off.",
            "Reactivation requires a new gate.",
        ],
    }


def test_deterministic_policy_derives_expected_statuses() -> None:
    result, corrections = comparison.apply_policy(None, _policy(), _case())
    statuses = {item.candidate_id: item.status for item in result.adjudications}

    assert statuses == _case()["expected"]
    assert corrections == []


def test_policy_overrides_bad_proposal_and_records_changes() -> None:
    proposal = comparison.phase5b.ProbeResult(
        relations=[],
        adjudications=[
            comparison.phase5b.ProposedAdjudication(
                candidate_id=candidate_id,
                status="historical",
                current_statement="The model ended reasoning with a historical label.",
                rationale="The proposal did not preserve the evidence distinction.",
                controlling_evidence_ids=[],
                review_required=False,
            )
            for candidate_id in _policy()["claims"]
        ],
        current_guidance="Further study is needed before deciding.",
    )

    result, corrections = comparison.apply_policy(proposal, _policy(), _case())

    assert {item.candidate_id: item.status for item in result.adjudications} == _case()["expected"]
    assert len(corrections) == 5
    assert corrections[-1]["candidate_id"] == "__current_guidance__"


def test_policy_rejects_unknown_traits() -> None:
    policy = _policy()
    policy["claims"]["mixed"]["trait"] = "invented"

    try:
        comparison.validate_policy(policy, _case())
    except ValueError as exc:
        assert "Unknown policy trait" in str(exc)
    else:
        raise AssertionError("unknown policy trait was accepted")


def test_few_shot_examples_are_unrelated_to_neural_case() -> None:
    examples_path = Path("docs/projects/knowledge_mvp/PHASE_5C_FEW_SHOT_EXAMPLES.json")
    text = examples_path.read_text(encoding="utf-8").casefold()

    assert "neural" not in text
    assert "titans" not in text
    assert "candidate-" not in text


def test_comparison_decision_attributes_policy_pass() -> None:
    arms = {
        "zero_shot": {"status": "fail", "unsupported_relation_count": 2},
        "few_shot": {"status": "fail", "unsupported_relation_count": 3},
        "few_shot_policy": {"status": "pass", "unsupported_relation_count": 3},
        "deterministic_only": {"status": "pass", "unsupported_relation_count": 0},
    }

    decision = comparison.comparison_decision(arms)

    assert decision.startswith("prefer deterministic-only")
