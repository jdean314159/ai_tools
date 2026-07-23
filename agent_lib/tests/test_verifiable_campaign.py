from __future__ import annotations

import hashlib
import json

import pytest

from agent_lib.eval.verifiable_campaign import (
    build_campaign_admission_manifest,
    build_shared_schema_pair_manifest,
    decide_campaign,
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
            "no_ledger": _result(exact=True, tokens=100, steps=2),
            "ledger": _result(exact=True, tokens=120, steps=3),
        },
        {
            "task_id": "intermediate",
            "tier": "intermediate",
            "no_ledger": _result(exact=False, tokens=200, steps=4),
            "ledger": _result(exact=False, tokens=180, steps=3),
        },
        {
            "task_id": "exploratory",
            "tier": "exploratory",
            "no_ledger": _result(exact=False, tokens=500, steps=10),
            "ledger": _result(exact=True, tokens=350, steps=7),
        },
    ]

    summary = summarize_paired_campaign(pairs)

    assert summary["primary_tier"] == "exploratory"
    assert summary["tiers"]["exploratory"]["paired_exact_outcomes"][
        "no_ledger_fail_ledger_pass"
    ] == 1
    assert summary["tiers"]["exploratory"][
        "median_ledger_minus_no_ledger_tokens"
    ] == -150
    assert summary["overall_equal_tier_macro"]["exact_rate_ledger"] == pytest.approx(
        2 / 3
    )
    assert summary["pooled_primary_result_prohibited"] is True


def test_paired_summary_rejects_incomplete_campaign_coverage() -> None:
    manifest = build_campaign_admission_manifest(_complete_admissions())
    one_pair = [
        {
            "task_id": "local-0",
            "tier": "local",
            "no_ledger": _result(exact=True, tokens=100, steps=2),
            "ledger": _result(exact=True, tokens=120, steps=3),
        }
    ]

    with pytest.raises(VerifiableNavigationError, match="exactly cover"):
        summarize_paired_campaign(one_pair, campaign_manifest=manifest)


def test_pair_manifest_holds_relation_schema_constant() -> None:
    shared = {
        "model": "qwen",
        "seed": 0,
        "budget": 120_000,
        "relation_claims_required": True,
        "relation_claim_schema_version": 1,
        "scoring_mode": "ast_relation_claims",
    }
    pair = build_shared_schema_pair_manifest(
        pair_id="pair-1",
        task_id="task-1",
        tier="exploratory",
        no_ledger_config={
            **shared,
            "ledger_enabled": False,
            "navigation_goals_enabled": False,
            "structured_navigation": False,
        },
        ledger_config={
            **shared,
            "ledger_enabled": True,
            "navigation_goals_enabled": True,
            "structured_navigation": True,
        },
        run_order=("no_ledger", "ledger"),
    )

    assert pair["comparison"] == "shared relation schema: no ledger vs ledger"
    with pytest.raises(VerifiableNavigationError, match="share task"):
        build_shared_schema_pair_manifest(
            pair_id="pair-2",
            task_id="task-1",
            tier="exploratory",
            no_ledger_config={
                **shared,
                "ledger_enabled": False,
                "navigation_goals_enabled": False,
                "structured_navigation": False,
            },
            ledger_config={
                **shared,
                "seed": 1,
                "ledger_enabled": True,
                "navigation_goals_enabled": True,
                "structured_navigation": True,
            },
            run_order=("ledger", "no_ledger"),
        )


def test_campaign_decision_uses_exploratory_pairs_and_cost_gate() -> None:
    pairs = []
    for index in range(6):
        no_ledger_exact = index >= 2
        pairs.append(
            {
                "task_id": f"explore-{index}",
                "tier": "exploratory",
                "no_ledger": {
                    **_result(
                        exact=no_ledger_exact,
                        tokens=100,
                        steps=5,
                    ),
                    "completed_with_answer": no_ledger_exact,
                },
                "ledger": _result(exact=True, tokens=90, steps=4),
            }
        )
    summary = summarize_paired_campaign(pairs)

    decision = decide_campaign(summary)

    assert decision["decision"] == "support_broader_shadow"
    assert decision["termination_net"] == 2
