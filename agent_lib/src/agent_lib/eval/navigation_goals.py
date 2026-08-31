"""Deterministic information-goal state for structured navigation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .navigation_claims import EvidenceRef


GoalStatus = Literal["open", "resolved", "abandoned"]


NAV_TEST_00_GOALS: tuple[tuple[str, str], ...] = (
    (
        "client_and_collection_initialization",
        "Identify persistent Chroma client initialization and collection initialization.",
    ),
    (
        "direct_collection_mutations",
        "Identify every direct Chroma collection mutation call such as upsert or delete.",
    ),
    (
        "pipeline_mutation_call_sites",
        "Identify each direct RAGPipeline call site invoking those storage mutations.",
    ),
)


NAVIGATION_GOAL_STATE_SCHEMA: dict[str, Any] = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "goal_id": {"type": "string", "minLength": 1},
            "requirement": {"type": "string", "minLength": 1},
            "status": {
                "type": "string",
                "enum": ["open", "resolved", "abandoned"],
            },
            "resolution_summary": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string", "minLength": 1},
                        "start_line": {"type": "integer", "minimum": 1},
                        "end_line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path", "start_line", "end_line"],
                },
            },
        },
        "required": [
            "goal_id",
            "requirement",
            "status",
            "resolution_summary",
            "evidence",
        ],
    },
}


@dataclass(frozen=True, slots=True)
class NavigationGoal:
    goal_id: str
    requirement: str
    status: GoalStatus = "open"
    resolution_summary: str = ""
    evidence: tuple[EvidenceRef, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NavigationGoal":
        evidence = value.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
        return cls(
            goal_id=str(value.get("goal_id") or ""),
            requirement=str(value.get("requirement") or ""),
            status=str(value.get("status") or ""),  # type: ignore[arg-type]
            resolution_summary=str(value.get("resolution_summary") or ""),
            evidence=tuple(
                EvidenceRef.from_mapping(item) for item in evidence if isinstance(item, Mapping)
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "requirement": self.requirement,
            "status": self.status,
            "resolution_summary": self.resolution_summary,
            "evidence": [
                {
                    "path": ref.path,
                    "start_line": ref.start_line,
                    "end_line": ref.end_line,
                }
                for ref in self.evidence
            ],
        }


def seed_navigation_goals(
    definitions: Sequence[tuple[str, str]] = NAV_TEST_00_GOALS,
) -> tuple[NavigationGoal, ...]:
    return tuple(
        NavigationGoal(goal_id=goal_id, requirement=requirement)
        for goal_id, requirement in definitions
    )


def validate_goal_transition(
    proposed: Sequence[NavigationGoal],
    *,
    previous: Sequence[NavigationGoal],
    observed_lines: Mapping[str, set[int]],
    action_kind: str,
    serves_goal_ids: Sequence[str],
) -> str | None:
    previous_by_id = {goal.goal_id: goal for goal in previous}
    proposed_by_id = {goal.goal_id: goal for goal in proposed}
    if set(proposed_by_id) != set(previous_by_id) or len(proposed) != len(previous):
        return "navigation goals cannot disappear, appear, or duplicate"
    for goal_id, prior in previous_by_id.items():
        current = proposed_by_id[goal_id]
        if current.requirement != prior.requirement:
            return f"navigation goal {goal_id} requirement changed"
        if current.status not in {"open", "resolved", "abandoned"}:
            return f"navigation goal {goal_id} has invalid status"
        if prior.status != "open" and current.status != prior.status:
            return f"navigation goal {goal_id} cannot transition from {prior.status}"
        if current.status == "open":
            if current.resolution_summary or current.evidence:
                return f"open navigation goal {goal_id} cannot have a resolution"
        elif current.status == "resolved":
            if not current.resolution_summary.strip() or not current.evidence:
                return f"resolved navigation goal {goal_id} requires summary and evidence"
            for ref in current.evidence:
                if (
                    ref.start_line < 1
                    or ref.end_line < ref.start_line
                    or not set(range(ref.start_line, ref.end_line + 1)).issubset(
                        observed_lines.get(ref.path, set())
                    )
                ):
                    return f"navigation goal {goal_id} references unobserved evidence"
        elif not current.resolution_summary.strip():
            return f"abandoned navigation goal {goal_id} requires a reason"

    open_ids = {goal.goal_id for goal in proposed if goal.status == "open"}
    if action_kind == "tool":
        if not serves_goal_ids:
            return "tool actions must serve at least one open navigation goal"
        if not set(serves_goal_ids).issubset(open_ids):
            return "tool action serves a navigation goal that is not open"
    elif action_kind == "final" and open_ids:
        return f"cannot finalize with open navigation goals: {sorted(open_ids)}"
    return None
