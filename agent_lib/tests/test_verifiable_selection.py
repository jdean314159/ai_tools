from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent_lib.eval.verifiable_selection import (
    CANDIDATE_ORDER_SALT,
    build_candidate_pool,
    select_campaign_candidates,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "nav_verifiable"


def _candidate(
    task_id: str,
    tier: str,
    *,
    snapshot: str,
    kind: str,
    decoys: int = 0,
    hops: int = 0,
    files: int = 1,
) -> dict:
    descriptor = {
        "snapshot_id": snapshot,
        "kind": kind,
        "path": "sample.py",
        "symbol": task_id,
        "endpoint": "",
        "line": None,
        "expected_relations": [{"kind": kind}],
    }
    return {
        **descriptor,
        "task_id": task_id,
        "question": task_id,
        "goal_requirements": [],
        "difficulty": {
            "hop_count": hops,
            "answer_file_count": files,
            "candidate_file_count": 5 if tier == "exploratory" else 1,
            "decoy_count": decoys,
            "tier": tier,
        },
        "selection_key": hashlib.sha256(
            (
                CANDIDATE_ORDER_SALT
                + json.dumps(descriptor, sort_keys=True, separators=(",", ":"))
            ).encode("utf-8")
        ).hexdigest(),
    }


def _selection_pool() -> dict:
    candidates = [
        *[
            _candidate(
                f"local-{index}",
                "local",
                snapshot="s1",
                kind="definition",
            )
            for index in range(4)
        ],
        *[
            _candidate(
                f"intermediate-{index}",
                "intermediate",
                snapshot="s2",
                kind="mutation_target",
            )
            for index in range(4)
        ],
        *[
            _candidate(
                f"decoy-{index}",
                "exploratory",
                snapshot=f"s{index + 1}",
                kind="direct_callers",
                decoys=4,
            )
            for index in range(3)
        ],
        *[
            _candidate(
                f"graph-{index}",
                "exploratory",
                snapshot=f"s{index + 1}",
                kind="call_path",
                hops=3,
                files=3,
            )
            for index in range(3)
        ],
    ]
    pool = {
        "schema_version": 1,
        "track": "NAV-VERIFIABLE-00",
        "selection_salt": CANDIDATE_ORDER_SALT,
        "snapshots": [],
        "candidates": sorted(candidates, key=lambda item: item["selection_key"]),
    }
    pool["candidate_pool_sha256"] = hashlib.sha256(
        json.dumps(pool, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return pool


def test_candidate_pool_enumeration_is_hashed_and_repeatable() -> None:
    first = build_candidate_pool([FIXTURE_ROOT])
    second = build_candidate_pool([FIXTURE_ROOT])

    assert first == second
    assert first["candidate_pool_sha256"]
    assert {item["kind"] for item in first["candidates"]} == {
        "definition",
        "direct_callers",
        "call_path",
        "mutation_target",
    }


def test_campaign_selection_is_deterministic_and_satisfies_frozen_counts() -> None:
    pool = _selection_pool()

    first = select_campaign_candidates(pool)
    second = select_campaign_candidates(pool)

    assert first == second
    assert len(first["selected_task_ids"]) == 14
    exploratory = [
        item
        for item in first["selected"]
        if item["difficulty"]["tier"] == "exploratory"
    ]
    assert len(exploratory) == 6
    assert len({item["snapshot_id"] for item in exploratory}) == 3
    assert first["candidate_selection_sha256"]
