from __future__ import annotations

from dataclasses import replace

from agent_lib.eval.navigation_claims import EvidenceRef
from agent_lib.eval.navigation_goals import (
    seed_navigation_goals,
    validate_goal_transition,
)


def test_finalization_is_rejected_while_required_goals_are_open() -> None:
    goals = seed_navigation_goals()

    error = validate_goal_transition(
        goals,
        previous=goals,
        observed_lines={},
        action_kind="final",
        serves_goal_ids=[],
    )

    assert error == (
        "cannot finalize with open navigation goals: "
        "['client_and_collection_initialization', 'direct_collection_mutations', "
        "'pipeline_mutation_call_sites']"
    )


def test_goals_cannot_disappear() -> None:
    goals = seed_navigation_goals()

    error = validate_goal_transition(
        goals[:-1],
        previous=goals,
        observed_lines={},
        action_kind="tool",
        serves_goal_ids=[goals[0].goal_id],
    )

    assert error == "navigation goals cannot disappear, appear, or duplicate"


def test_resolution_requires_observed_evidence() -> None:
    goals = seed_navigation_goals()
    proposed = (
        replace(
            goals[0],
            status="resolved",
            resolution_summary="Found initialization.",
            evidence=(EvidenceRef("module.py", 10, 10),),
        ),
        *goals[1:],
    )

    error = validate_goal_transition(
        proposed,
        previous=goals,
        observed_lines={},
        action_kind="tool",
        serves_goal_ids=[goals[1].goal_id],
    )

    assert error == (
        "navigation goal client_and_collection_initialization references unobserved evidence"
    )


def test_valid_completion_allows_finalization() -> None:
    goals = seed_navigation_goals()
    proposed = tuple(
        replace(
            goal,
            status="resolved",
            resolution_summary=f"Resolved {goal.goal_id}.",
            evidence=(EvidenceRef("module.py", index, index),),
        )
        for index, goal in enumerate(goals, start=1)
    )

    error = validate_goal_transition(
        proposed,
        previous=goals,
        observed_lines={"module.py": {1, 2, 3}},
        action_kind="final",
        serves_goal_ids=[],
    )

    assert error is None
