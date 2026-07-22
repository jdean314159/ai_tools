#!/usr/bin/env python3
"""Replay serialized NAV-TEST-00 agent steps through the action guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from action_trajectory_loop_guard import assess_trajectory, detect_and_redirect


def replay(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    guard_meta = record["run"].get("meta", {}).get("action_guard", {})
    detector_trace = guard_meta.get("detector_trace", {})
    captured_actions = detector_trace.get("actions")
    run_steps = record["run"]["steps"]
    steps = captured_actions if isinstance(captured_actions, list) and captured_actions else run_steps
    replay_source = "captured_detector_input" if steps is captured_actions else "reconstructed_run_steps"
    calls = record["planner_usage"]["calls"]
    first_fire = None
    for step_count in range(1, len(steps) + 1):
        intervention = detect_and_redirect(steps[:step_count])
        if intervention is None:
            continue
        first_fire = {
            "step": step_count,
            "cumulative_actual_tokens": sum(
                int(call["actual_total_tokens"])
                for call in calls[: min(step_count, len(calls))]
            ),
            "truncation_point": intervention.truncation_point,
            "loop_start_action": intervention.loop_start_action,
            "confirmation_actions": intervention.confirmation_actions,
            "evidence_novelty": intervention.evidence_novelty,
            "repeated_action": intervention.repeated_action,
        }
        break
    return {
        "path": str(path),
        "replay_source": replay_source,
        "stop_reason": record["run"]["stop_reason"],
        "planner_calls": len(calls),
        "cumulative_actual_tokens": sum(int(call["actual_total_tokens"]) for call in calls),
        "first_fire": first_fire,
        "fidelity": _compare_captured_decisions(steps, detector_trace),
        "reconstruction": _compare_reconstructed_input(run_steps, captured_actions),
    }


def _compare_captured_decisions(steps: list[object], detector_trace: object) -> dict[str, Any] | None:
    if not isinstance(detector_trace, dict) or not isinstance(detector_trace.get("decisions"), list):
        return None
    recorded = detector_trace["decisions"]
    mismatches = []
    for step_count, item in enumerate(recorded, start=1):
        replayed = assess_trajectory(steps[:step_count])
        replayed_decision = replayed.action_assessments[-1] if replayed.action_assessments else None
        replayed_intervention = replayed.as_dict()["intervention"]
        recorded_intervention = item.get("intervention") if isinstance(item, dict) else None
        if replayed_decision != item.get("decision") or replayed_intervention != recorded_intervention:
            mismatches.append(step_count)
    return {"checks": len(recorded), "matching": not mismatches, "mismatch_checks": mismatches}


def _compare_reconstructed_input(
    run_steps: list[object], captured_actions: object
) -> dict[str, Any] | None:
    if not isinstance(captured_actions, list) or not captured_actions:
        return None
    reconstructed = list(assess_trajectory(run_steps).actions)
    mismatch_actions = []
    for position in range(max(len(reconstructed), len(captured_actions))):
        reconstructed_action = reconstructed[position] if position < len(reconstructed) else None
        captured_action = captured_actions[position] if position < len(captured_actions) else None
        if reconstructed_action != captured_action:
            mismatch_actions.append(position + 1)
    return {
        "captured_actions": len(captured_actions),
        "reconstructed_actions": len(reconstructed),
        "matching": not mismatch_actions,
        "mismatch_actions": mismatch_actions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_records", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([replay(path) for path in args.run_records], indent=2))


if __name__ == "__main__":
    main()
