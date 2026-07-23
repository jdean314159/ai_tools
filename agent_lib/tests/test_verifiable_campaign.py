from __future__ import annotations

import hashlib
import json

import pytest

from agent_lib.eval.verifiable_campaign import (
    build_campaign_admission_manifest,
    summarize_paired_campaign,
)
from agent_lib.eval.verifiable_navigation import VerifiableNavigationError


def _admission(snapshot: int, tasks: list[dict]) -> dict:
    manifest = {
        "schema_version": 1,
        "track": "NAV-VERIFIABLE-00",
        "difficulty_policy": {},
        "source_hashes": {f"snapshot_{snapshot}.py": f"hash-{snapshot}"},
        "tasks": tasks,
    }
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest["admission_manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return manifest


def _task(
    task_id: str,
    tier: str,
    *,
    kind: str = "definition",
    hops: int = 0,
    files: int = 1,
    candidates: int = 1,
    decoys: int = 0,
) -> dict:
    return {
        "task_id": task_id,
        "kind": kind,
        "oracle_resolvable": True,
        "canonical_symbols_unique": True,
        "difficulty": {
            "hop_count": hops,
            "answer_file_count": files,
            "candidate_file_count": candidates,
            "decoy_count": decoys,
            "tier": tier,
        },
        "expected_relations": [{"kind": "definition"}],
    }


def _complete_admissions() -> list[dict]:
    return [
        _admission(
            1,
            [
                *[_task(f"local-{index}", "local") for index in range(4)],
                _task(
                    "explore-decoy-0",
                    "exploratory",
                    kind="direct_callers",
                    candidates=5,
                    decoys=4,
                ),
                _task(
                    "explore-graph-0",
                    "exploratory",
                    kind="call_path",
                    hops=3,
                    files=3,
                    candidates=2,
                ),
            ],
        ),
        _admission(
            2,
            [
                *[
                    _task(
                        f"intermediate-{index}",
                        "intermediate",
                        candidates=2,
                        decoys=1,
                    )
                    for index in range(4)
                ],
                _task(
                    "explore-decoy-1",
                    "exploratory",
                    kind="direct_callers",
                    candidates=5,
                    decoys=4,
                ),
                _task(
                    "explore-graph-1",
                    "exploratory",
                    kind="call_path",
                    hops=3,
                    files=3,
                    candidates=2,
                ),
            ],
        ),
        _admission(
            3,
            [
                _task(
                    "explore-decoy-2",
                    "exploratory",
                    kind="direct_callers",
                    candidates=5,
                    decoys=4,
                ),
                _task(
                    "explore-graph-2",
                    "exploratory",
                    kind="call_path",
                    hops=3,
                    files=3,
                    candidates=2,
                ),
            ],
        ),
    ]


def test_campaign_admission_requires_balanced_frozen_distribution() -> None:
    manifest = build_campaign_admission_manifest(_complete_admissions())

    assert manifest["complete"] is True
    assert manifest["task_counts"] == {
        "exploratory": 6,
        "intermediate": 4,
        "local": 4,
    }
    assert manifest["snapshot_count"] == 3
    assert len(manifest["campaign_manifest_sha256"]) == 64


def test_campaign_admission_rejects_insufficient_exploratory_evidence() -> None:
    admissions = _complete_admissions()
    admissions[-1] = _admission(3, [])

    with pytest.raises(VerifiableNavigationError, match="exploratory tasks"):
        build_campaign_admission_manifest(admissions)


def test_campaign_admission_rejects_one_dominant_exploratory_shape() -> None:
    admissions = _complete_admissions()
    for admission in admissions:
        for task in admission["tasks"]:
            if task["difficulty"]["tier"] == "exploratory":
                task["kind"] = "call_path"
        unhashed = {
            key: value
            for key, value in admission.items()
            if key != "admission_manifest_sha256"
        }
        admission["admission_manifest_sha256"] = hashlib.sha256(
            json.dumps(
                unhashed, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    with pytest.raises(VerifiableNavigationError, match="more than half"):
        build_campaign_admission_manifest(admissions)


def _result(*, exact: bool, tokens: int, steps: int) -> dict:
    return {
        "completed_with_answer": True,
        "relation_correct": exact,
        "evidence_complete": exact,
        "evidence_precise": exact,
        "exact_correct": exact,
        "tokens": tokens,
        "tool_steps": steps,
    }


def test_paired_summary_keeps_tiers_separate_and_uses_equal_tier_macro() -> None:
    pairs = [
        {
            "task_id": "local",
            "tier": "local",
            "autonomous": _result(exact=True, tokens=100, steps=2),
            "structured": _result(exact=True, tokens=120, steps=3),
        },
        {
            "task_id": "intermediate",
            "tier": "intermediate",
            "autonomous": _result(exact=False, tokens=200, steps=4),
            "structured": _result(exact=False, tokens=180, steps=3),
        },
        {
            "task_id": "exploratory",
            "tier": "exploratory",
            "autonomous": _result(exact=False, tokens=500, steps=10),
            "structured": _result(exact=True, tokens=350, steps=7),
        },
    ]

    summary = summarize_paired_campaign(pairs)

    assert summary["primary_tier"] == "exploratory"
    assert summary["tiers"]["exploratory"]["paired_exact_outcomes"][
        "autonomous_fail_structured_pass"
    ] == 1
    assert summary["tiers"]["exploratory"][
        "median_structured_minus_autonomous_tokens"
    ] == -150
    assert summary["overall_equal_tier_macro"]["exact_rate_structured"] == pytest.approx(
        2 / 3
    )
    assert summary["pooled_primary_result_prohibited"] is True


def test_paired_summary_rejects_incomplete_campaign_coverage() -> None:
    manifest = build_campaign_admission_manifest(_complete_admissions())
    one_pair = [
        {
            "task_id": "local-0",
            "tier": "local",
            "autonomous": _result(exact=True, tokens=100, steps=2),
            "structured": _result(exact=True, tokens=120, steps=3),
        }
    ]

    with pytest.raises(VerifiableNavigationError, match="exactly cover"):
        summarize_paired_campaign(one_pair, campaign_manifest=manifest)
