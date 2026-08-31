from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).with_name("review_knowledge_candidates.py")
SPEC = importlib.util.spec_from_file_location(
    "review_knowledge_candidates",
    SCRIPT_PATH,
)
assert SPEC is not None
review = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = review
SPEC.loader.exec_module(review)


def _candidate(candidate_id: str, conversation: str = "c1") -> dict:
    return {
        "candidate_id": candidate_id,
        "review_status": "pending",
        "batch_id": "b1",
        "conversation_uuid": conversation,
        "statement": "Evaluation should use explicit tasks and failure criteria.",
        "scope": "LLM application evaluation",
        "evidence_kind": "secondary_assessment",
        "qualifications": ["Metrics should be task-specific."],
        "source_refs": ["r000001p001"],
    }


def _corpus() -> list[dict]:
    return [
        {
            "conversation_uuid": "c1",
            "message_uuid": "m1",
            "sender": "assistant",
            "source_kind": "message_text",
            "source_index": None,
            "raw_sha256": "raw",
            "normalized_sha256": "normalized",
            "normalized_text": "Source evidence supporting evaluation criteria.",
        }
    ]


def _decision(action: str, candidate_ids: list[str], claims: list[dict] | None = None):
    return review.ReviewDecision(
        event_id=f"event-{action}",
        recorded_at="2026-06-13T12:00:00+00:00",
        reviewer="human",
        action=action,
        candidate_ids=candidate_ids,
        rationale="Reviewed against the source evidence.",
        claims=claims or [],
    )


def test_queue_contains_bounded_evidence_and_topic() -> None:
    queue = review.build_review_queue([_candidate("candidate-1")], _corpus())

    assert len(queue) == 1
    assert queue[0]["topic"] == "evaluation"
    assert queue[0]["evidence"][0]["message_uuid"] == "m1"
    assert "Source evidence" in queue[0]["evidence"][0]["excerpt"]


def test_decision_shapes_are_strict() -> None:
    with pytest.raises(ValueError, match="at least two candidates"):
        _decision(
            "consolidate",
            ["candidate-1"],
            [
                {
                    "statement": "A consolidated statement that is long enough.",
                    "scope": "LLM evaluation",
                    "evidence_kind": "secondary_assessment",
                }
            ],
        )


def test_append_decision_rejects_unknown_candidate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown candidate"):
        review.append_decision(
            tmp_path / "decisions.jsonl",
            _decision("approve", ["missing"]),
            {"candidate-1"},
        )


def test_append_decision_is_append_only_and_rejects_duplicate_event(
    tmp_path: Path,
) -> None:
    path = tmp_path / "decisions.jsonl"
    decision = _decision("approve", ["candidate-1"])

    review.append_decision(path, decision, {"candidate-1"})

    with pytest.raises(ValueError, match="Duplicate event"):
        review.append_decision(path, decision, {"candidate-1"})
    assert len(review.load_jsonl(path)) == 1


def test_materialize_uses_latest_decision(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    approved = tmp_path / "approved.jsonl"
    manifest = tmp_path / "manifest.json"
    candidates.write_text(json.dumps(_candidate("candidate-1")) + "\n")
    decisions.write_text(
        json.dumps(_decision("approve", ["candidate-1"]).model_dump())
        + "\n"
        + json.dumps(
            review.ReviewDecision(
                event_id="event-reject-later",
                recorded_at="2026-06-13T13:00:00+00:00",
                reviewer="human",
                action="reject",
                candidate_ids=["candidate-1"],
                rationale="Later review found the claim too broad.",
            ).model_dump()
        )
        + "\n"
    )
    manifest.write_text(json.dumps({"candidate_count": 1}))

    result = review.materialize_approved(
        candidates_path=candidates,
        decisions_path=decisions,
        approved_path=approved,
        review_manifest_path=manifest,
    )

    assert result["approved_claim_count"] == 0
    assert result["review_complete"] is True
    assert approved.read_text() == ""


def test_consolidation_emits_one_claim_with_union_provenance(tmp_path: Path) -> None:
    first = _candidate("candidate-1")
    second = {
        **_candidate("candidate-2"),
        "source_refs": ["r000002p001"],
    }
    candidates = tmp_path / "candidates.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    approved = tmp_path / "approved.jsonl"
    manifest = tmp_path / "manifest.json"
    candidates.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
    consolidated = _decision(
        "consolidate",
        ["candidate-1", "candidate-2"],
        [
            {
                "statement": "Architecture evaluations should use explicit tasks and failure criteria.",
                "scope": "LLM application architecture reviews",
                "evidence_kind": "secondary_assessment",
                "qualifications": ["Use task-specific metrics and preserve exceptions."],
            }
        ],
    )
    decisions.write_text(json.dumps(consolidated.model_dump()) + "\n")
    manifest.write_text(json.dumps({"candidate_count": 2}))

    result = review.materialize_approved(
        candidates_path=candidates,
        decisions_path=decisions,
        approved_path=approved,
        review_manifest_path=manifest,
    )
    rows = review.load_jsonl(approved)

    assert result["approved_claim_count"] == 1
    assert rows[0]["source_candidate_ids"] == ["candidate-1", "candidate-2"]
    assert rows[0]["source_refs"] == ["r000001p001", "r000002p001"]


def test_later_source_decision_supersedes_whole_consolidation(tmp_path: Path) -> None:
    first = _candidate("candidate-1")
    second = {**_candidate("candidate-2"), "source_refs": ["r000002p001"]}
    candidates = tmp_path / "candidates.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    approved = tmp_path / "approved.jsonl"
    manifest = tmp_path / "manifest.json"
    candidates.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
    consolidation = _decision(
        "consolidate",
        ["candidate-1", "candidate-2"],
        [
            {
                "statement": "Architecture evaluations should use explicit tasks and failure criteria.",
                "scope": "LLM application architecture reviews",
                "evidence_kind": "secondary_assessment",
            }
        ],
    )
    later_reject = review.ReviewDecision(
        event_id="event-later-reject",
        recorded_at="2026-06-13T14:00:00+00:00",
        reviewer="human",
        action="reject",
        candidate_ids=["candidate-2"],
        rationale="The second source does not support consolidation.",
    )
    decisions.write_text(
        json.dumps(consolidation.model_dump()) + "\n" + json.dumps(later_reject.model_dump()) + "\n"
    )
    manifest.write_text(json.dumps({"candidate_count": 2}))

    result = review.materialize_approved(
        candidates_path=candidates,
        decisions_path=decisions,
        approved_path=approved,
        review_manifest_path=manifest,
    )

    assert result["approved_claim_count"] == 0
