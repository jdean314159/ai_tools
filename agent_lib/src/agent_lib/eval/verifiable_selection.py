"""Mechanical candidate enumeration and selection for NAV-VERIFIABLE-00."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .verifiable_campaign import CAMPAIGN_TIER_MINIMUMS
from .verifiable_navigation import (
    PythonRelationOracle,
    RelationCanonicalizer,
    VerifiableNavigationError,
    VerifiableTask,
    classify_task_difficulty,
)


CANDIDATE_POOL_SCHEMA_VERSION = 2
CANDIDATE_SELECTION_SCHEMA_VERSION = 2
CANDIDATE_ORDER_SALT = "NAV-VERIFIABLE-00-candidate-order-v2"
REQUIRED_TASK_KINDS = frozenset(
    {"definition", "direct_callers", "call_path", "mutation_target"}
)


def build_candidate_pool(snapshot_roots: Sequence[str | Path]) -> dict[str, Any]:
    """Enumerate every v1-oracle-resolvable task from pinned snapshot roots."""

    candidates: list[dict[str, Any]] = []
    snapshot_records: list[dict[str, Any]] = []
    for raw_root in snapshot_roots:
        root = Path(raw_root).resolve(strict=True)
        oracle = PythonRelationOracle(root)
        canonicalizer = RelationCanonicalizer(oracle)
        source_hashes = {
            path.relative_to(root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(root.rglob("*.py"))
        }
        snapshot_id = _sha256_json(source_hashes)
        snapshot_records.append(
            {"snapshot_id": snapshot_id, "source_hashes": source_hashes}
        )
        seen_relations: set[str] = set()
        for task in _enumerate_snapshot_tasks(oracle, canonicalizer):
            expected = tuple(
                canonicalizer.relation(item) for item in oracle.expected(task)
            )
            relation_payload = [
                {
                    "kind": item.kind,
                    "path": item.path,
                    "symbol": item.symbol,
                    "target": item.target,
                    "path_symbols": list(item.path_symbols),
                    "required_lines": list(item.required_lines),
                }
                for item in expected
            ]
            relation_key = _sha256_json(
                {"snapshot_id": snapshot_id, "relations": relation_payload}
            )
            if relation_key in seen_relations:
                continue
            seen_relations.add(relation_key)
            descriptor = {
                "snapshot_id": snapshot_id,
                "kind": task.kind,
                "path": task.path,
                "symbol": task.symbol,
                "endpoint": task.endpoint,
                "line": task.line,
                "expected_relations": relation_payload,
            }
            task_id = f"navv-{_sha256_json(descriptor)[:16]}"
            difficulty = classify_task_difficulty(task, oracle=oracle)
            candidates.append(
                {
                    **descriptor,
                    "task_id": task_id,
                    "question": task.question,
                    "goal_requirements": [
                        {"goal_id": goal_id, "requirement": requirement}
                        for goal_id, requirement in task.goal_requirements
                    ],
                    "difficulty": difficulty.as_dict(),
                    "selection_key": hashlib.sha256(
                        (
                            CANDIDATE_ORDER_SALT
                            + json.dumps(
                                descriptor, sort_keys=True, separators=(",", ":")
                            )
                        ).encode("utf-8")
                    ).hexdigest(),
                }
            )
    manifest: dict[str, Any] = {
        "schema_version": CANDIDATE_POOL_SCHEMA_VERSION,
        "track": "NAV-VERIFIABLE-00",
        "selection_salt": CANDIDATE_ORDER_SALT,
        "snapshots": sorted(snapshot_records, key=lambda item: item["snapshot_id"]),
        "candidates": sorted(candidates, key=lambda item: item["selection_key"]),
    }
    manifest["candidate_pool_sha256"] = _sha256_json(manifest)
    return manifest


def select_campaign_candidates(pool: Mapping[str, Any]) -> dict[str, Any]:
    """Select a complete campaign mechanically from the frozen candidate pool."""

    supplied_hash = str(pool.get("candidate_pool_sha256") or "")
    unhashed = {
        key: value for key, value in pool.items() if key != "candidate_pool_sha256"
    }
    if supplied_hash != _sha256_json(unhashed):
        raise VerifiableNavigationError("candidate pool hash mismatch")
    candidates = [
        dict(item)
        for item in pool.get("candidates") or []
        if isinstance(item, Mapping)
    ]
    by_tier = {
        tier: sorted(
            [
                item
                for item in candidates
                if dict(item.get("difficulty") or {}).get("tier") == tier
            ],
            key=lambda item: str(item["selection_key"]),
        )
        for tier in CAMPAIGN_TIER_MINIMUMS
    }
    selected = [
        *by_tier["local"][: CAMPAIGN_TIER_MINIMUMS["local"]],
        *by_tier["intermediate"][: CAMPAIGN_TIER_MINIMUMS["intermediate"]],
    ]
    if len(selected) < 8:
        raise VerifiableNavigationError(
            "candidate pool does not supply local/intermediate minimums"
        )
    exploratory = _select_exploratory(
        by_tier["exploratory"],
        CAMPAIGN_TIER_MINIMUMS["exploratory"],
        covered_kinds={str(item["kind"]) for item in selected},
    )
    selected.extend(exploratory)
    selected_kinds = {str(item["kind"]) for item in selected}
    if selected_kinds != REQUIRED_TASK_KINDS:
        raise VerifiableNavigationError(
            "candidate pool cannot supply every required task shape"
        )
    manifest: dict[str, Any] = {
        "schema_version": CANDIDATE_SELECTION_SCHEMA_VERSION,
        "track": "NAV-VERIFIABLE-00",
        "candidate_pool_sha256": supplied_hash,
        "selection_method": "coverage-greedy then fixed salted hash order",
        "selected_task_ids": [str(item["task_id"]) for item in selected],
        "selected": selected,
    }
    manifest["candidate_selection_sha256"] = _sha256_json(manifest)
    return manifest


def _select_exploratory(
    candidates: Sequence[dict[str, Any]],
    count: int,
    *,
    covered_kinds: set[str],
) -> list[dict[str, Any]]:
    remaining = list(candidates)
    selected: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()
    snapshots: set[str] = set()
    decoy_tasks = 0
    graph_tasks = 0
    while len(selected) < count:
        allowed = [
            item
            for item in remaining
            if kind_counts[str(item.get("kind") or "")] < count // 2
        ]
        if not allowed:
            raise VerifiableNavigationError(
                "candidate pool cannot satisfy exploratory shape diversity"
            )

        def coverage(item: Mapping[str, Any]) -> tuple[int, str]:
            difficulty = dict(item.get("difficulty") or {})
            gain = 0
            if len(snapshots) < 3 and str(item.get("snapshot_id")) not in snapshots:
                gain += 1
            if decoy_tasks < 3 and int(difficulty.get("decoy_count") or 0) >= 4:
                gain += 1
            if graph_tasks < 3 and (
                int(difficulty.get("hop_count") or 0) >= 3
                or int(difficulty.get("answer_file_count") or 0) >= 3
            ):
                gain += 1
            if (
                len(covered_kinds) < len(REQUIRED_TASK_KINDS)
                and str(item.get("kind") or "") not in covered_kinds
            ):
                gain += 1
            return (-gain, str(item["selection_key"]))

        chosen = min(allowed, key=coverage)
        selected.append(chosen)
        remaining.remove(chosen)
        kind_counts[str(chosen.get("kind") or "")] += 1
        covered_kinds.add(str(chosen.get("kind") or ""))
        snapshots.add(str(chosen.get("snapshot_id") or ""))
        difficulty = dict(chosen.get("difficulty") or {})
        decoy_tasks += int(int(difficulty.get("decoy_count") or 0) >= 4)
        graph_tasks += int(
            int(difficulty.get("hop_count") or 0) >= 3
            or int(difficulty.get("answer_file_count") or 0) >= 3
        )
    if len(snapshots) < 3 or decoy_tasks < 3 or graph_tasks < 3:
        raise VerifiableNavigationError(
            "candidate pool cannot satisfy exploratory snapshot/feature diversity"
        )
    return selected


def _enumerate_snapshot_tasks(
    oracle: PythonRelationOracle,
    canonicalizer: RelationCanonicalizer,
) -> list[VerifiableTask]:
    tasks: list[VerifiableTask] = []
    definitions = sorted(oracle.definitions.values(), key=lambda item: item.symbol)
    for definition in definitions:
        symbol = canonicalizer.symbol(definition.symbol)
        tasks.append(
            VerifiableTask(
                task_id="candidate",
                kind="definition",
                question=f"Locate the definition of {symbol}.",
                path=definition.path,
                symbol=symbol,
                goal_requirements=(("locate_definition", f"Locate {symbol}."),),
            )
        )
        if oracle.direct_callers(path=definition.path, symbol=definition.symbol):
            tasks.append(
                VerifiableTask(
                    task_id="candidate",
                    kind="direct_callers",
                    question=f"Identify the syntactically direct callers of {symbol}.",
                    path=definition.path,
                    symbol=symbol,
                    goal_requirements=(
                        ("identify_direct_callers", f"Find direct callers of {symbol}."),
                    ),
                )
            )
    for start in definitions:
        for end in definitions:
            if start.symbol == end.symbol or start.path != end.path:
                continue
            try:
                relation = oracle.unique_call_path(
                    path=start.path,
                    symbol=start.symbol,
                    endpoint=end.symbol,
                )
            except VerifiableNavigationError:
                continue
            if len(relation.path_symbols) < 2:
                continue
            start_symbol = canonicalizer.symbol(start.symbol)
            end_symbol = canonicalizer.symbol(end.symbol)
            tasks.append(
                VerifiableTask(
                    task_id="candidate",
                    kind="call_path",
                    question=f"Trace the call path from {start_symbol} to {end_symbol}.",
                    path=start.path,
                    symbol=start_symbol,
                    endpoint=end_symbol,
                    goal_requirements=(
                        (
                            "trace_call_path",
                            f"Trace {start_symbol} to {end_symbol}.",
                        ),
                    ),
                )
            )
    for call in sorted(oracle.calls, key=lambda item: (item.path, item.line, item.caller)):
        caller = canonicalizer.symbol(call.caller)
        tasks.append(
            VerifiableTask(
                task_id="candidate",
                kind="mutation_target",
                question=f"Identify the callable invoked by {caller} at line {call.line}.",
                path=call.path,
                symbol=caller,
                line=call.line,
                goal_requirements=(
                    (
                        "identify_named_site_target",
                        f"Identify the callable at {caller} line {call.line}.",
                    ),
                ),
            )
        )
    return tasks


def _sha256_json(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(canonical).hexdigest()
