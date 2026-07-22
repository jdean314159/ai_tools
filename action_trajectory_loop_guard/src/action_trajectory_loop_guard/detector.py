"""Detect repeated low-novelty tool actions without agent or engine coupling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import PurePosixPath
from typing import Any


_WARMUP_TOOL_ACTIONS = 8
_CONFIRMATION_ACTIONS = 2
_READ_OVERLAP_THRESHOLD = 0.50
_NOVELTY_THRESHOLD = 0.10
_TRAILING_COMPARISON_ACTIONS = 12
_REDIRECT_INSTRUCTION = (
    "The recent tool actions are repeating without adding evidence. Preserve the "
    "evidence already gathered and finalize the answer now."
)


@dataclass(frozen=True, slots=True)
class Intervention:
    """Advice returned after a confirmed action loop.

    ``truncation_point`` is a zero-based sequence offset. The caller retains
    trajectory entries before it and may discard entries from it onward.
    """

    truncation_point: int
    instruction: str
    loop_start_action: int
    confirmation_actions: int
    evidence_novelty: float
    repeated_action: str


@dataclass(frozen=True, slots=True)
class DetectorAssessment:
    """JSON-safe detector input and decision state for one trajectory check."""

    schema_version: int
    actions: tuple[dict[str, Any], ...]
    action_assessments: tuple[dict[str, Any], ...]
    intervention: Intervention | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "actions": [dict(action) for action in self.actions],
            "action_assessments": [dict(item) for item in self.action_assessments],
            "intervention": asdict(self.intervention) if self.intervention is not None else None,
        }


@dataclass(frozen=True, slots=True)
class _Action:
    sequence_offset: int
    action_number: int
    tool: str
    arguments: dict[str, Any]
    success: bool
    outcome_category: str | None
    evidence: frozenset[tuple[str, int | None]]


@dataclass(frozen=True, slots=True)
class _Assessment:
    action: _Action
    duplicate: bool
    novelty: float

    @property
    def redundant(self) -> bool:
        return self.duplicate and self.novelty <= _NOVELTY_THRESHOLD


def detect_and_redirect(action_trajectory: Sequence[object] | Iterable[object]) -> Intervention | None:
    """Return redirect advice for a confirmed low-novelty action loop."""

    return assess_trajectory(action_trajectory).intervention


def assess_trajectory(
    action_trajectory: Sequence[object] | Iterable[object],
) -> DetectorAssessment:
    """Return the canonical detector input and every intermediate decision.

    The serialized ``actions`` can be passed back to this function directly.
    This makes live-versus-replay equivalence testable without reconstructing
    detector inputs from a more general run-record schema.
    """

    events = list(action_trajectory)
    actions = [
        action
        for offset, event in enumerate(events)
        if (action := _extract_action(event, offset)) is not None
    ]
    snapshots = tuple(_serialize_action(action) for action in actions)

    seen_evidence: set[tuple[str, int | None]] = set()
    assessments: list[_Assessment] = []
    serialized_assessments: list[dict[str, Any]] = []
    intervention = None
    for position, action in enumerate(actions):
        novelty = _novelty(action.evidence, seen_evidence)
        prior = actions[max(0, position - _TRAILING_COMPARISON_ACTIONS) : position]
        duplicate_actions = [
            candidate.action_number for candidate in prior if _near_duplicate(action, candidate)
        ]
        assessment = _Assessment(
            action=action,
            duplicate=bool(duplicate_actions),
            novelty=novelty,
        )
        assessments.append(assessment)
        serialized_assessments.append(
            {
                "action_number": action.action_number,
                "sequence_offset": action.sequence_offset,
                "comparison_window": [candidate.action_number for candidate in prior],
                "near_duplicate_actions": duplicate_actions,
                "evidence_atoms": len(action.evidence),
                "novel_evidence_atoms": len(action.evidence - seen_evidence),
                "novelty": novelty,
                "redundant": assessment.redundant,
            }
        )
        seen_evidence.update(action.evidence)

        # Both confirming actions must follow the completed warmup. With
        # zero-based positions, the second confirmer is warmup + 1.
        if position < _WARMUP_TOOL_ACTIONS + 1:
            continue
        if position == 0 or not assessment.redundant:
            continue
        previous = assessments[position - 1]
        confirmed_pair = previous.redundant or (
            previous.novelty <= _NOVELTY_THRESHOLD
            and _near_duplicate(assessment.action, previous.action)
        )
        if confirmed_pair and intervention is None:
            intervention = Intervention(
                truncation_point=previous.action.sequence_offset,
                instruction=_REDIRECT_INSTRUCTION,
                loop_start_action=previous.action.action_number,
                confirmation_actions=_CONFIRMATION_ACTIONS,
                evidence_novelty=max(previous.novelty, assessment.novelty),
                repeated_action=_signature(previous.action),
            )
    return DetectorAssessment(
        schema_version=1,
        actions=snapshots,
        action_assessments=tuple(serialized_assessments),
        intervention=intervention,
    )


def _extract_action(event: object, offset: int) -> _Action | None:
    action = _field(event, "action")
    if action is None or _field(action, "kind") != "tool":
        return None
    call = _field(action, "tool_call")
    if call is None:
        return None
    tool = _field(call, "name")
    arguments = _field(call, "arguments")
    if not isinstance(tool, str) or not isinstance(arguments, Mapping):
        raise TypeError(f"trajectory event {offset} has an invalid tool call")

    observation = _field(event, "observation")
    result = _field(observation, "tool_result") if observation is not None else None
    success = bool(_field(result, "success")) if result is not None else False
    result_meta = _field(result, "meta") if result is not None else None
    observation_meta = _field(observation, "meta") if observation is not None else None
    meta = result_meta if isinstance(result_meta, Mapping) else observation_meta
    typed_meta = meta if isinstance(meta, Mapping) else {}
    evidence = _evidence_atoms(typed_meta)
    category = typed_meta.get("category")
    number = _field(event, "index")
    action_number = int(number) if isinstance(number, int) else offset + 1
    return _Action(
        sequence_offset=offset,
        action_number=action_number,
        tool=tool,
        arguments=dict(arguments),
        success=success,
        outcome_category=str(category) if category is not None else None,
        evidence=frozenset(evidence),
    )


def _serialize_action(action: _Action) -> dict[str, Any]:
    evidence = [
        {"path": path, "line": line}
        for path, line in sorted(
            action.evidence,
            key=lambda atom: (atom[0], -1 if atom[1] is None else atom[1]),
        )
    ]
    return {
        "index": action.action_number,
        "action": {
            "kind": "tool",
            "tool_call": {"name": action.tool, "arguments": dict(action.arguments)},
        },
        "observation": {
            "tool_result": {
                "success": action.success,
                "meta": {
                    "category": action.outcome_category,
                    "evidence": [
                        {"path": item["path"], "lines": [] if item["line"] is None else [item["line"]]}
                        for item in evidence
                    ],
                },
            }
        },
    }


def _field(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _canonical_path(value: object) -> str:
    text = str(value or ".").replace("\\", "/")
    normalized = PurePosixPath(text).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized or "."


def _evidence_atoms(meta: Mapping[str, object]) -> set[tuple[str, int | None]]:
    atoms: set[tuple[str, int | None]] = set()
    evidence = meta.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, Mapping) or "path" not in item:
                continue
            path = _canonical_path(item["path"])
            lines = item.get("lines")
            if isinstance(lines, list) and lines:
                atoms.update((path, int(line)) for line in lines if isinstance(line, int))
            else:
                atoms.add((path, None))
    paths = meta.get("paths")
    if isinstance(paths, list):
        atoms.update((_canonical_path(path), None) for path in paths if isinstance(path, str))
    return atoms


def _novelty(
    evidence: frozenset[tuple[str, int | None]],
    seen: set[tuple[str, int | None]],
) -> float:
    if not evidence:
        return 0.0
    novel = evidence - seen
    return len(novel) / len(evidence)


def _near_duplicate(current: _Action, prior: _Action) -> bool:
    if current.tool != prior.tool:
        return False
    if current.tool == "read_file":
        if _canonical_path(current.arguments.get("path")) != _canonical_path(prior.arguments.get("path")):
            return False
        current_range = _read_range(current.arguments)
        prior_range = _read_range(prior.arguments)
        if current_range is None or prior_range is None:
            return _normalized_arguments(current.arguments) == _normalized_arguments(prior.arguments)
        overlap = max(0, min(current_range[1], prior_range[1]) - max(current_range[0], prior_range[0]) + 1)
        smaller = min(current_range[1] - current_range[0] + 1, prior_range[1] - prior_range[0] + 1)
        return overlap / smaller >= _READ_OVERLAP_THRESHOLD
    return _normalized_arguments(current.arguments) == _normalized_arguments(prior.arguments)


def _read_range(arguments: Mapping[str, Any]) -> tuple[int, int] | None:
    if arguments.get("full") is True:
        return None
    start = arguments.get("start_line", 1)
    count = arguments.get("line_count")
    if not isinstance(start, int) or not isinstance(count, int) or count < 1:
        return None
    return start, start + count - 1


def _normalized_arguments(arguments: Mapping[str, Any]) -> str:
    ignored = {"max_matches", "max_results", "line_count", "start_line"}
    normalized = {
        key: (_canonical_path(value) if key == "path" else value)
        for key, value in arguments.items()
        if key not in ignored
    }
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)


def _signature(action: _Action) -> str:
    return f"{action.tool} {_normalized_arguments(action.arguments)}"
