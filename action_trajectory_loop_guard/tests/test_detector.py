from __future__ import annotations

from agent_lib import AgentAction, AgentObservation, AgentStep, ToolResult
from action_trajectory_loop_guard import Intervention, assess_trajectory, detect_and_redirect


def _read(index: int, start: int, *, path: str = "module.py", success: bool = True) -> AgentStep:
    lines = list(range(start, start + 100)) if success else []
    result = ToolResult(
        name="read_file",
        output="result",
        success=success,
        meta={
            "category": "ok" if success else "result_too_large",
            "paths": [path] if success else [],
            "evidence": [{"path": path, "lines": lines}] if success else [],
        },
    )
    return AgentStep(
        index=index,
        action=AgentAction.tool(
            "read_file", {"path": path, "start_line": start, "line_count": 100}
        ),
        observation=AgentObservation(kind="tool_result", text="result", tool_result=result),
    )


def test_detects_two_confirmed_redundant_reads_after_warmup() -> None:
    trajectory = [_read(index, 1 + (index - 1) * 100) for index in range(1, 9)]
    trajectory.extend((_read(9, 1), _read(10, 1)))

    result = detect_and_redirect(trajectory)

    assert isinstance(result, Intervention)
    assert result.truncation_point == 8
    assert result.loop_start_action == 9
    assert result.confirmation_actions == 2
    assert result.evidence_novelty == 0.0
    assert "finalize" in result.instruction


def test_progressive_overlapping_reads_do_not_fire() -> None:
    trajectory = [_read(index, 1 + (index - 1) * 90) for index in range(1, 16)]

    assert detect_and_redirect(trajectory) is None


def test_early_failed_retries_can_recover_without_false_positive() -> None:
    trajectory = [
        _read(1, 1, success=False),
        _read(2, 1, success=False),
        _read(3, 1, success=False),
    ]
    trajectory.extend(_read(index, 1 + (index - 4) * 100) for index in range(4, 12))

    assert detect_and_redirect(trajectory) is None


def test_repeated_failed_actions_after_warmup_are_confirmed() -> None:
    trajectory = [_read(index, 1 + (index - 1) * 100) for index in range(1, 9)]
    trajectory.extend((_read(9, 900, success=False), _read(10, 900, success=False)))

    result = detect_and_redirect(trajectory)

    assert result is not None
    assert result.loop_start_action == 9


def test_accepts_serialized_agent_steps() -> None:
    trajectory = []
    for index in range(1, 9):
        trajectory.append(
            {
                "index": index,
                "action": {
                    "kind": "tool",
                    "tool_call": {
                        "name": "grep",
                        "arguments": {"path": ".", "pattern": f"unique_{index}"},
                    },
                },
                "observation": {
                    "tool_result": {
                        "success": True,
                        "meta": {"evidence": [{"path": "module.py", "lines": [index]}]},
                    }
                },
            }
        )
    repeated = {
        "action": {
            "kind": "tool",
            "tool_call": {"name": "grep", "arguments": {"path": ".", "pattern": "same"}},
        },
        "observation": {"tool_result": {"success": True, "meta": {"evidence": []}}},
    }
    trajectory.extend(({"index": 9, **repeated}, {"index": 10, **repeated}))

    assert detect_and_redirect(trajectory) is not None


def test_captured_detector_actions_replay_exactly() -> None:
    trajectory = [_read(index, 1 + (index - 1) * 100) for index in range(1, 4)]
    trajectory.append(AgentStep(index=4, action=AgentAction.message_only("continue")))
    trajectory.extend(_read(index, 1 + (index - 2) * 100) for index in range(5, 10))
    trajectory.extend((_read(10, 1), _read(11, 1)))

    live = assess_trajectory(trajectory)
    replayed = assess_trajectory(live.as_dict()["actions"])

    assert replayed.as_dict() == live.as_dict()
    assert live.actions[3]["_detector_sequence_offset"] == 4
    assert live.action_assessments[-1]["near_duplicate_actions"] == [1, 10]


def test_messages_and_final_actions_are_ignored() -> None:
    trajectory = [
        AgentStep(index=1, action=AgentAction.message_only("retry")),
        AgentStep(index=2, action=AgentAction.final("done")),
    ]

    assert detect_and_redirect(trajectory) is None
