"""Frozen campaign-level policy and summaries for NAV-VERIFIABLE-00."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .verifiable_navigation import VerifiableNavigationError


VERIFIABLE_CAMPAIGN_SCHEMA_VERSION = 1
CAMPAIGN_TIER_MINIMUMS = {
    "local": 4,
    "intermediate": 4,
    "exploratory": 6,
}
EXPLORATORY_MINIMUM_SNAPSHOTS = 3
EXPLORATORY_MINIMUM_DECOY_TASKS = 3
EXPLORATORY_MINIMUM_GRAPH_TASKS = 3


def build_shared_schema_pair_manifest(
    *,
    pair_id: str,
    task_id: str,
    tier: str,
    no_ledger_config: Mapping[str, Any],
    ledger_config: Mapping[str, Any],
    run_order: Sequence[str],
) -> dict[str, Any]:
    """Freeze the only admissible arm difference: per-step goal ledger state."""

    if tuple(run_order) not in {
        ("no_ledger", "ledger"),
        ("ledger", "no_ledger"),
    }:
        raise VerifiableNavigationError("run_order must contain no_ledger and ledger exactly once")
    if tier not in CAMPAIGN_TIER_MINIMUMS:
        raise VerifiableNavigationError("pair requires a frozen valid tier")
    ignored = {
        "ledger_enabled",
        "structured_navigation",
        "navigation_goals_enabled",
        "output_dir",
        "run_label",
    }
    left = {key: value for key, value in no_ledger_config.items() if key not in ignored}
    right = {key: value for key, value in ledger_config.items() if key not in ignored}
    if left != right:
        raise VerifiableNavigationError(
            "paired arms must share task, model, schema, scorer, budget, and decoding"
        )
    required_shared = {
        "relation_claims_required": True,
        "scoring_mode": "ast_relation_claims",
    }
    for key, expected in required_shared.items():
        if left.get(key) != expected:
            raise VerifiableNavigationError(f"paired arms require shared {key}={expected!r}")
    if not left.get("relation_claim_schema_version"):
        raise VerifiableNavigationError("paired arms require a relation claim schema version")
    if (
        no_ledger_config.get("ledger_enabled") is not False
        or no_ledger_config.get("navigation_goals_enabled") is not False
        or no_ledger_config.get("structured_navigation") is not False
    ):
        raise VerifiableNavigationError("no_ledger arm cannot enable goal ledger")
    if (
        ledger_config.get("ledger_enabled") is not True
        or ledger_config.get("navigation_goals_enabled") is not True
        or ledger_config.get("structured_navigation") is not True
    ):
        raise VerifiableNavigationError("ledger arm must enable goal ledger")
    return {
        "schema_version": 1,
        "track": "NAV-VERIFIABLE-00",
        "pair_id": pair_id,
        "task_id": task_id,
        "tier": tier,
        "comparison": "shared relation schema: no ledger vs ledger",
        "run_order": list(run_order),
        "shared_config": left,
        "arms": {
            "no_ledger": dict(no_ledger_config),
            "ledger": dict(ledger_config),
        },
    }


def build_campaign_admission_manifest(
    admission_manifests: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate and combine pre-run task-admission manifests."""

    tasks: list[dict[str, Any]] = []
    snapshot_ids: set[str] = set()
    for admission in admission_manifests:
        if admission.get("track") != "NAV-VERIFIABLE-00":
            raise VerifiableNavigationError("unexpected admission track")
        if admission.get("schema_version") != 1:
            raise VerifiableNavigationError("unsupported admission schema version")
        supplied_hash = str(admission.get("admission_manifest_sha256") or "")
        unhashed = {
            key: value for key, value in admission.items() if key != "admission_manifest_sha256"
        }
        actual_hash = _sha256_json(unhashed)
        if supplied_hash != actual_hash:
            raise VerifiableNavigationError("admission manifest hash mismatch")
        source_hashes = admission.get("source_hashes")
        if not isinstance(source_hashes, Mapping) or not source_hashes:
            raise VerifiableNavigationError("admission requires source hashes")
        snapshot_id = _sha256_json(source_hashes)
        snapshot_ids.add(snapshot_id)
        for task in admission.get("tasks") or []:
            if not isinstance(task, Mapping):
                raise VerifiableNavigationError("admission task must be an object")
            if not bool(task.get("oracle_resolvable")) or not bool(
                task.get("canonical_symbols_unique")
            ):
                raise VerifiableNavigationError(
                    "campaign tasks must pass oracle and canonical admission"
                )
            tier = str(dict(task.get("difficulty") or {}).get("tier") or "")
            if tier not in CAMPAIGN_TIER_MINIMUMS:
                raise VerifiableNavigationError("campaign task has invalid frozen tier")
            tasks.append({**dict(task), "snapshot_id": snapshot_id})

    task_ids = [str(task.get("task_id") or "") for task in tasks]
    if not task_ids or any(not task_id for task_id in task_ids):
        raise VerifiableNavigationError("campaign tasks require task ids")
    if len(set(task_ids)) != len(task_ids):
        raise VerifiableNavigationError("campaign task ids must be unique")

    tiers = Counter(str(dict(task.get("difficulty") or {}).get("tier") or "") for task in tasks)
    for tier, minimum in CAMPAIGN_TIER_MINIMUMS.items():
        if tiers[tier] < minimum:
            raise VerifiableNavigationError(f"campaign requires at least {minimum} {tier} tasks")

    exploratory = [
        task for task in tasks if dict(task.get("difficulty") or {}).get("tier") == "exploratory"
    ]
    exploratory_snapshots = {str(task["snapshot_id"]) for task in exploratory}
    if len(exploratory_snapshots) < EXPLORATORY_MINIMUM_SNAPSHOTS:
        raise VerifiableNavigationError(
            "exploratory tasks require at least three fixture snapshots"
        )
    kind_counts = Counter(str(task.get("kind") or "") for task in exploratory)
    if kind_counts and max(kind_counts.values()) * 2 > len(exploratory):
        raise VerifiableNavigationError(
            "one task shape cannot supply more than half the exploratory tier"
        )
    decoy_tasks = sum(
        int(dict(task.get("difficulty") or {}).get("decoy_count") or 0) >= 4 for task in exploratory
    )
    if decoy_tasks < EXPLORATORY_MINIMUM_DECOY_TASKS:
        raise VerifiableNavigationError(
            "exploratory tier requires at least three decoy-threshold tasks"
        )
    graph_tasks = sum(
        int(dict(task.get("difficulty") or {}).get("hop_count") or 0) >= 3
        or int(dict(task.get("difficulty") or {}).get("answer_file_count") or 0) >= 3
        for task in exploratory
    )
    if graph_tasks < EXPLORATORY_MINIMUM_GRAPH_TASKS:
        raise VerifiableNavigationError(
            "exploratory tier requires at least three graph/multi-file tasks"
        )

    manifest: dict[str, Any] = {
        "schema_version": VERIFIABLE_CAMPAIGN_SCHEMA_VERSION,
        "track": "NAV-VERIFIABLE-00",
        "complete": True,
        "minimums": dict(CAMPAIGN_TIER_MINIMUMS),
        "task_counts": dict(sorted(tiers.items())),
        "snapshot_count": len(snapshot_ids),
        "tasks": sorted(tasks, key=lambda item: str(item["task_id"])),
    }
    manifest["campaign_manifest_sha256"] = _sha256_json(manifest)
    return manifest


def summarize_paired_campaign(
    pairs: Sequence[Mapping[str, Any]],
    *,
    campaign_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize paired outcomes per tier; overall values are equal-tier macros."""

    by_tier: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    task_ids: set[str] = set()
    for pair in pairs:
        task_id = str(pair.get("task_id") or "")
        tier = str(pair.get("tier") or "")
        if not task_id or task_id in task_ids:
            raise VerifiableNavigationError("paired records require unique task ids")
        if tier not in CAMPAIGN_TIER_MINIMUMS:
            raise VerifiableNavigationError("paired record has invalid tier")
        for mode in ("no_ledger", "ledger"):
            if not isinstance(pair.get(mode), Mapping):
                raise VerifiableNavigationError(f"paired record requires {mode} result")
        task_ids.add(task_id)
        by_tier[tier].append(pair)

    if campaign_manifest is not None:
        expected = {
            str(task.get("task_id") or ""): str(
                dict(task.get("difficulty") or {}).get("tier") or ""
            )
            for task in campaign_manifest.get("tasks") or []
            if isinstance(task, Mapping)
        }
        actual = {str(pair.get("task_id") or ""): str(pair.get("tier") or "") for pair in pairs}
        if actual != expected:
            raise VerifiableNavigationError(
                "paired records must exactly cover the admitted campaign tasks and tiers"
            )

    tier_summaries = {tier: _summarize_tier(records) for tier, records in sorted(by_tier.items())}
    rate_fields = (
        "termination_rate_no_ledger",
        "termination_rate_ledger",
        "relation_rate_no_ledger",
        "relation_rate_ledger",
        "evidence_complete_rate_no_ledger",
        "evidence_complete_rate_ledger",
        "evidence_precise_rate_no_ledger",
        "evidence_precise_rate_ledger",
        "exact_rate_no_ledger",
        "exact_rate_ledger",
    )
    macro = (
        {
            field: statistics.fmean(float(summary[field]) for summary in tier_summaries.values())
            for field in rate_fields
        }
        if tier_summaries
        else {}
    )
    return {
        "schema_version": 1,
        "track": "NAV-VERIFIABLE-00",
        "primary_tier": "exploratory",
        "tiers": tier_summaries,
        "overall_equal_tier_macro": macro,
        "pooled_primary_result_prohibited": True,
        "campaign_complete": (
            bool(campaign_manifest.get("complete")) if campaign_manifest is not None else None
        ),
    }


def decide_campaign(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the frozen exploratory-tier directional decision rule."""

    exploratory = dict(dict(summary.get("tiers") or {}).get("exploratory") or {})
    if int(exploratory.get("task_count") or 0) < 6:
        return {
            "decision": "incomplete",
            "reason": "fewer than six exploratory pairs",
        }
    termination = dict(exploratory.get("paired_termination_outcomes") or {})
    exact = dict(exploratory.get("paired_exact_outcomes") or {})
    relation = dict(exploratory.get("paired_relation_outcomes") or {})
    termination_net = int(termination.get("no_ledger_fail_ledger_pass") or 0) - int(
        termination.get("no_ledger_pass_ledger_fail") or 0
    )
    exact_net = int(exact.get("no_ledger_fail_ledger_pass") or 0) - int(
        exact.get("no_ledger_pass_ledger_fail") or 0
    )
    relation_net = int(relation.get("no_ledger_fail_ledger_pass") or 0) - int(
        relation.get("no_ledger_pass_ledger_fail") or 0
    )
    no_ledger_tokens = float(exploratory.get("total_tokens_no_ledger") or 0)
    ledger_tokens = float(exploratory.get("total_tokens_ledger") or 0)
    token_ratio = ledger_tokens / no_ledger_tokens if no_ledger_tokens > 0 else float("inf")
    median_overhead = exploratory.get("median_both_complete_ledger_token_overhead_fraction")
    task_count = int(exploratory.get("task_count") or 0)
    termination_ceiling = (
        int(termination.get("both_pass") or 0) == task_count
        and int(termination.get("no_ledger_pass_ledger_fail") or 0) == 0
        and int(termination.get("no_ledger_fail_ledger_pass") or 0) == 0
    )

    support = (
        termination_net >= 2
        and int(termination.get("no_ledger_pass_ledger_fail") or 0) <= 1
        and exact_net >= 0
        and relation_net >= 0
        and token_ratio <= 1.0
        and isinstance(median_overhead, (int, float))
        and float(median_overhead) <= 0.25
    )
    quality_or_cost_reject = (
        exact_net <= -2 or relation_net <= -2 or (token_ratio > 1.25 and exact_net <= 0)
    )
    termination_reject = termination_net <= 0 and not termination_ceiling
    reject = quality_or_cost_reject or termination_reject
    return {
        "decision": (
            "support_broader_shadow"
            if support
            else "reject_ledger_direction"
            if reject
            else "inconclusive_schema_ceiling"
            if termination_ceiling
            else "inconclusive"
        ),
        "termination_ceiling": termination_ceiling,
        "termination_net": termination_net,
        "exact_net": exact_net,
        "relation_net": relation_net,
        "exploratory_token_ratio": token_ratio,
        "median_both_complete_ledger_token_overhead_fraction": median_overhead,
    }


def _summarize_tier(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(records)

    def rate(mode: str, field: str) -> float:
        return sum(bool(dict(record[mode]).get(field)) for record in records) / count

    exact_outcomes = Counter()
    relation_outcomes = Counter()
    termination_outcomes = Counter()
    token_deltas: list[float] = []
    step_deltas: list[float] = []
    both_complete_overheads: list[float] = []
    total_tokens = {"no_ledger": 0.0, "ledger": 0.0}
    for record in records:
        no_ledger = dict(record["no_ledger"])
        ledger = dict(record["ledger"])
        for field, counter in (
            ("exact_correct", exact_outcomes),
            ("relation_correct", relation_outcomes),
            ("completed_with_answer", termination_outcomes),
        ):
            counter[_paired_outcome(bool(no_ledger.get(field)), bool(ledger.get(field)))] += 1
        if isinstance(no_ledger.get("tokens"), (int, float)) and isinstance(
            ledger.get("tokens"), (int, float)
        ):
            total_tokens["no_ledger"] += float(no_ledger["tokens"])
            total_tokens["ledger"] += float(ledger["tokens"])
            token_deltas.append(float(ledger["tokens"]) - float(no_ledger["tokens"]))
            if (
                bool(no_ledger.get("completed_with_answer"))
                and bool(ledger.get("completed_with_answer"))
                and float(no_ledger["tokens"]) > 0
            ):
                both_complete_overheads.append(
                    (float(ledger["tokens"]) - float(no_ledger["tokens"]))
                    / float(no_ledger["tokens"])
                )
        if isinstance(no_ledger.get("tool_steps"), (int, float)) and isinstance(
            ledger.get("tool_steps"), (int, float)
        ):
            step_deltas.append(float(ledger["tool_steps"]) - float(no_ledger["tool_steps"]))
    return {
        "task_count": count,
        "termination_rate_no_ledger": rate("no_ledger", "completed_with_answer"),
        "termination_rate_ledger": rate("ledger", "completed_with_answer"),
        "relation_rate_no_ledger": rate("no_ledger", "relation_correct"),
        "relation_rate_ledger": rate("ledger", "relation_correct"),
        "evidence_complete_rate_no_ledger": rate("no_ledger", "evidence_complete"),
        "evidence_complete_rate_ledger": rate("ledger", "evidence_complete"),
        "evidence_precise_rate_no_ledger": rate("no_ledger", "evidence_precise"),
        "evidence_precise_rate_ledger": rate("ledger", "evidence_precise"),
        "exact_rate_no_ledger": rate("no_ledger", "exact_correct"),
        "exact_rate_ledger": rate("ledger", "exact_correct"),
        "paired_termination_outcomes": _ordered_outcomes(termination_outcomes),
        "paired_relation_outcomes": _ordered_outcomes(relation_outcomes),
        "paired_exact_outcomes": {
            **_ordered_outcomes(exact_outcomes),
        },
        "total_tokens_no_ledger": total_tokens["no_ledger"],
        "total_tokens_ledger": total_tokens["ledger"],
        "median_ledger_minus_no_ledger_tokens": (
            statistics.median(token_deltas) if token_deltas else None
        ),
        "individual_token_deltas": token_deltas,
        "median_both_complete_ledger_token_overhead_fraction": (
            statistics.median(both_complete_overheads) if both_complete_overheads else None
        ),
        "median_ledger_minus_no_ledger_tool_steps": (
            statistics.median(step_deltas) if step_deltas else None
        ),
        "individual_tool_step_deltas": step_deltas,
    }


def _paired_outcome(no_ledger: bool, ledger: bool) -> str:
    if no_ledger and ledger:
        return "both_pass"
    if ledger:
        return "no_ledger_fail_ledger_pass"
    if no_ledger:
        return "no_ledger_pass_ledger_fail"
    return "both_fail"


def _ordered_outcomes(counter: Counter[str]) -> dict[str, int]:
    return {
        key: counter[key]
        for key in (
            "no_ledger_fail_ledger_pass",
            "no_ledger_pass_ledger_fail",
            "both_pass",
            "both_fail",
        )
    }


def _sha256_json(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
