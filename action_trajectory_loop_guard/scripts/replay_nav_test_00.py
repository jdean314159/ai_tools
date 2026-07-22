#!/usr/bin/env python3
"""Replay serialized NAV-TEST-00 agent steps through the action guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from action_trajectory_loop_guard import detect_and_redirect


def replay(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    steps = record["run"]["steps"]
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
        "stop_reason": record["run"]["stop_reason"],
        "planner_calls": len(calls),
        "cumulative_actual_tokens": sum(int(call["actual_total_tokens"]) for call in calls),
        "first_fire": first_fire,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_records", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([replay(path) for path in args.run_records], indent=2))


if __name__ == "__main__":
    main()
