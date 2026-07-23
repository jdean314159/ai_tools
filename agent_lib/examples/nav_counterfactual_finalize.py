#!/usr/bin/env python3
"""Counterfactual evidence-centric finalization for a recorded NAV run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from agent_lib.eval.repo_navigation import (
    FINALIZATION_ACTION_SCHEMA,
    FINALIZATION_SYSTEM_PROMPT,
    LlamaServerClient,
)
from agent_lib.llm_engines_adapter import extract_json_object
from llm_engines.contracts import ChatMessage, GenerationRequest


_SOURCE_LINE = re.compile(r"^(\d+): ?(.*)$")
_PATH = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.py")
_RELEVANCE_TERMS = (
    "chroma",
    "persistentclient",
    "create_collection",
    "get_or_create_collection",
    ".upsert(",
    ".delete(",
    "delete_collection(",
    "delete_by_source(",
    "_store.add(",
    "_store.prune(",
    "_make_client(",
)


def _enclosing_headers(lines: dict[int, str], number: int) -> set[int]:
    """Retain observable symbol names needed to classify a matched call."""

    selected: set[int] = set()
    hit_indent = len(lines[number]) - len(lines[number].lstrip())
    method_indent = hit_indent
    for candidate in sorted((line for line in lines if line < number), reverse=True):
        text = lines[candidate]
        stripped = text.lstrip()
        indent = len(text) - len(stripped)
        if stripped.startswith(("def ", "async def ")) and indent < method_indent:
            selected.update({candidate - 1, candidate})
            method_indent = indent
            break
    for candidate in sorted((line for line in lines if line < number), reverse=True):
        text = lines[candidate]
        stripped = text.lstrip()
        indent = len(text) - len(stripped)
        if stripped.startswith("class ") and indent < method_indent:
            selected.update({candidate - 1, candidate})
            break
    return selected


def _observed_source(record: dict[str, Any], action_cutoff: int, *, context_lines: int = 6) -> str:
    files: dict[str, dict[int, str]] = {}
    tool_actions = 0
    for step in record["run"]["steps"]:
        action = step["action"]
        call = action.get("tool_call")
        if action.get("kind") != "tool" or not isinstance(call, dict):
            continue
        tool_actions += 1
        if tool_actions > action_cutoff:
            break
        observation = step.get("observation") or {}
        result = observation.get("tool_result") or {}
        if call.get("name") != "read_file" or not result.get("success"):
            continue
        path = str((call.get("arguments") or {}).get("path") or "")
        parsed: dict[int, str] = {}
        for raw_line in str(observation.get("text") or "").splitlines():
            match = _SOURCE_LINE.match(raw_line)
            if match:
                parsed[int(match.group(1))] = match.group(2)
        files.setdefault(path, {}).update(parsed)

    sections: list[str] = []
    for path, lines in sorted(files.items()):
        selected: set[int] = set()
        for number, text in lines.items():
            if any(term in text.lower() for term in _RELEVANCE_TERMS):
                selected.update(range(number - context_lines, number + context_lines + 1))
                selected.update(_enclosing_headers(lines, number))
        retained = sorted(number for number in selected if number in lines)
        if not retained:
            continue
        rendered = [f"{number}: {lines[number]}" for number in retained]
        sections.append(f"### {path}\n" + "\n".join(rendered))
    return "\n\n".join(sections)


def _cumulative_tokens(record: dict[str, Any], action_cutoff: int) -> int:
    tool_actions = 0
    cutoff_step = 0
    for step in record["run"]["steps"]:
        action = step["action"]
        if action.get("kind") == "tool" and isinstance(action.get("tool_call"), dict):
            tool_actions += 1
            if tool_actions == action_cutoff:
                cutoff_step = int(step["index"])
                break
    calls = record["planner_usage"]["calls"]
    return sum(int(call["actual_total_tokens"]) for call in calls[:cutoff_step])


def _surfaced_regions(
    record: dict[str, Any], regions: list[dict[str, Any]], action_cutoff: int
) -> set[str]:
    surfaced: set[str] = set()
    tool_actions = 0
    for step in record["run"]["steps"]:
        action = step["action"]
        if action.get("kind") != "tool" or not isinstance(action.get("tool_call"), dict):
            continue
        tool_actions += 1
        if tool_actions > action_cutoff:
            break
        result = ((step.get("observation") or {}).get("tool_result") or {})
        for evidence in (result.get("meta") or {}).get("evidence") or []:
            evidence_lines = set(int(line) for line in evidence.get("lines") or [])
            for region in regions:
                relevant = range(int(region["start_line"]), int(region["end_line"]) + 1)
                if evidence.get("path") == region["path"] and evidence_lines.intersection(relevant):
                    surfaced.add(str(region["id"]))
    return surfaced


def _score_answer(
    answer: str, regions: list[dict[str, Any]], surfaced: set[str]
) -> dict[str, Any]:
    correct = set()
    for region in regions:
        terms = [str(term).lower() for term in region.get("required_answer_terms") or []]
        if region["path"] in answer and all(term in answer.lower() for term in terms):
            correct.add(str(region["id"]))
    known_paths = {str(region["path"]) for region in regions}
    mentioned_paths = set(_PATH.findall(answer))
    surfaced_correct = correct & surfaced
    return {
        "surfaced_region_ids": sorted(surfaced),
        "correct_region_ids": sorted(correct),
        "surfaced_correct_region_ids": sorted(surfaced_correct),
        "evidence_conditioned_recall": (
            len(surfaced_correct) / len(surfaced) if surfaced else 0.0
        ),
        "full_answer_recall": len(correct) / len(regions) if regions else 0.0,
        "unsupported_paths": sorted(mentioned_paths - known_paths),
    }


def run_cutoff(
    *,
    client: LlamaServerClient,
    record: dict[str, Any],
    question: str,
    regions: list[dict[str, Any]],
    action_cutoff: int,
) -> dict[str, Any]:
    evidence = _observed_source(record, action_cutoff)
    user_prompt = (
        f"Task:\n{question}\n\n"
        "Observed source evidence (and only this evidence):\n"
        f"{evidence}\n\n"
        "Conclude from the observed evidence now. No tools are available.\n"
        "Before answering, account for every observed qualifying call in each requested "
        "category: client or storage initialization, collection creation, direct mutation, "
        "and pipeline mutation call site. Include pipeline construction of the persistent "
        "storage implementation when observed. Exclude retrieval-only calls such as "
        "get_collection, count, get, and query. Do not imply that an unobserved call site "
        "was found. List only supported qualifying locations and classifications."
    )
    messages = [
        ChatMessage(role="system", content=FINALIZATION_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_prompt),
    ]
    prompt_tokens = client.count_messages(messages)
    consumed_tokens = _cumulative_tokens(record, action_cutoff)
    remaining_tokens = 120_000 - consumed_tokens
    max_output = min(2_048, 40_000 - prompt_tokens, remaining_tokens - prompt_tokens)
    if max_output < 512:
        return {
            "action_cutoff": action_cutoff,
            "outcome": "budget_unavailable",
            "consumed_tokens": consumed_tokens,
            "remaining_tokens": remaining_tokens,
            "prompt_tokens": prompt_tokens,
            "max_output_tokens": max_output,
            "user_prompt": user_prompt,
        }
    response = client.generate(
        GenerationRequest(
            messages=messages,
            max_tokens=max_output,
            temperature=0.0,
            json_schema=FINALIZATION_ACTION_SCHEMA,
            metadata={
                "eval": "NAV-TEST-00-counterfactual-finalization",
                "action_cutoff": action_cutoff,
                "tools_enabled": False,
            },
        )
    )
    payload = extract_json_object(response.message.content or "")
    answer = str(payload.get("final_output") or "").strip()
    surfaced = _surfaced_regions(record, regions, action_cutoff)
    return {
        "action_cutoff": action_cutoff,
        "outcome": "success" if payload.get("kind") == "final" and answer else "no_answer",
        "consumed_tokens": consumed_tokens,
        "remaining_tokens": remaining_tokens,
        "prompt_tokens": prompt_tokens,
        "max_output_tokens": max_output,
        "actual_input_tokens": response.usage.input_tokens,
        "actual_output_tokens": response.usage.output_tokens,
        "answer": answer,
        "score": _score_answer(answer, regions, surfaced),
        "user_prompt": user_prompt,
        "raw_response": response.message.content,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-record", required=True, type=Path)
    parser.add_argument("--answer-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cutoffs", default="17,19")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"output already exists: {args.output}")
    record = json.loads(args.run_record.read_text(encoding="utf-8"))
    answer_key = json.loads(args.answer_key.read_text(encoding="utf-8"))
    client = LlamaServerClient(args.base_url, seed=args.seed)
    results = [
        run_cutoff(
            client=client,
            record=record,
            question=str(answer_key["question"]),
            regions=list(answer_key["regions"]),
            action_cutoff=int(cutoff),
        )
        for cutoff in args.cutoffs.split(",")
    ]
    output = {
        "schema_version": 1,
        "run_record": str(args.run_record),
        "answer_key": str(args.answer_key),
        "seed": args.seed,
        "cutoffs": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps([{key: value for key, value in item.items() if key not in {"user_prompt", "raw_response"}} for item in results], indent=2))


if __name__ == "__main__":
    main()
