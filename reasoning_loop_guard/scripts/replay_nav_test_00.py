#!/usr/bin/env python3
"""Replay NAV-TEST-00 run records through the v1 loop detector.

This diagnostic intentionally checks two candidate text streams:

* ``response_text``: the exact decoded JSON returned by the model;
* ``action_text``: the parsed action message, tool name, and arguments.

Neither is a typed reasoning stream. Comparing both makes the current
integration gap visible rather than silently treating JSON syntax as reasoning.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reasoning_loop_guard import Intervention, detect_and_redirect


def _action_text(step: dict[str, Any]) -> str:
    action = step["action"]
    tool_call = action.get("tool_call") or {}
    return " ".join(
        (
            str(action.get("message") or ""),
            str(tool_call.get("name") or ""),
            json.dumps(tool_call.get("arguments") or {}, sort_keys=True),
        )
    )


def _first_fire(fragments: list[str], calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = ""
    cumulative_tokens = 0
    for call_index, (fragment, call) in enumerate(zip(fragments, calls), start=1):
        text += fragment + "\n"
        cumulative_tokens += int(call["actual_total_tokens"])
        intervention = detect_and_redirect(text)
        if intervention is not None:
            return _fire_record(call_index, cumulative_tokens, len(text), intervention)
    return None


def _fire_record(
    call_index: int,
    cumulative_tokens: int,
    stream_characters: int,
    intervention: Intervention,
) -> dict[str, Any]:
    return {
        "call_index": call_index,
        "cumulative_actual_tokens": cumulative_tokens,
        "stream_characters": stream_characters,
        "truncation_point": intervention.truncation_point,
        "loop_start_token": intervention.loop_start_token,
        "repetition_fraction": intervention.repetition_fraction,
    }


def replay(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    calls = record["planner_usage"]["calls"]
    # A completed final action has a planner call; a budget-stop final action is
    # synthesized by the harness and does not. The prefix aligns both forms.
    steps = record["run"]["steps"][: len(calls)]
    if len(calls) != len(steps):
        raise ValueError(
            f"{path}: {len(calls)} planner calls do not match {len(steps)} model steps"
        )

    return {
        "path": str(path),
        "stop_reason": record["run"]["stop_reason"],
        "planner_calls": len(calls),
        "cumulative_actual_tokens": sum(int(call["actual_total_tokens"]) for call in calls),
        "thinking_disabled": record["config"]["decoding"].get("thinking_disabled"),
        "decoded_response_first_fire": _first_fire(
            [str(call["response_text"]) for call in calls], calls
        ),
        "parsed_action_first_fire": _first_fire([_action_text(step) for step in steps], calls),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_records", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([replay(path) for path in args.run_records], indent=2))


if __name__ == "__main__":
    main()
