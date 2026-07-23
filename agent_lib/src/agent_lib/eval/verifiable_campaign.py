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
            key: value
            for key, value in admission.items()
            if key != "admission_manifest_sha256"
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
                raise VerifiableNavigationError(
                    "campaign task has invalid frozen tier"
                )
            tasks.append({**dict(task), "snapshot_id": snapshot_id})

    task_ids = [str(task.get("task_id") or "") for task in tasks]
    if not task_ids or any(not task_id for task_id in task_ids):
        raise VerifiableNavigationError("campaign tasks require task ids")
    if len(set(task_ids)) != len(task_ids):
        raise VerifiableNavigationError("campaign task ids must be unique")

    tiers = Counter(
        str(dict(task.get("difficulty") or {}).get("tier") or "")
        for task in tasks
    )
    for tier, minimum in CAMPAIGN_TIER_MINIMUMS.items():
        if tiers[tier] < minimum:
            raise VerifiableNavigationError(
                f"campaign requires at least {minimum} {tier} tasks"
            )

    exploratory = [
        task
        for task in tasks
        if dict(task.get("difficulty") or {}).get("tier") == "exploratory"
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
        int(dict(task.get("difficulty") or {}).get("decoy_count") or 0) >= 4
        for task in exploratory
    )
    if decoy_tasks < EXPLORATORY_MINIMUM_DECOY_TASKS:
        raise VerifiableNavigationError(
            "exploratory tier requires at least three decoy-threshold tasks"
        )
    graph_tasks = sum(
        int(dict(task.get("difficulty") or {}).get("hop_count") or 0) >= 3
        or int(dict(task.get("difficulty") or {}).get("answer_file_count") or 0)
        >= 3
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
        for mode in ("autonomous", "structured"):
            if not isinstance(pair.get(mode), Mapping):
                raise VerifiableNavigationError(
                    f"paired record requires {mode} result"
                )
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
        actual = {
            str(pair.get("task_id") or ""): str(pair.get("tier") or "")
            for pair in pairs
        }
        if actual != expected:
            raise VerifiableNavigationError(
                "paired records must exactly cover the admitted campaign tasks and tiers"
            )

    tier_summaries = {
        tier: _summarize_tier(records)
        for tier, records in sorted(by_tier.items())
    }
    rate_fields = (
        "termination_rate_autonomous",
        "termination_rate_structured",
        "relation_rate_autonomous",
        "relation_rate_structured",
        "evidence_complete_rate_autonomous",
        "evidence_complete_rate_structured",
        "evidence_precise_rate_autonomous",
        "evidence_precise_rate_structured",
        "exact_rate_autonomous",
        "exact_rate_structured",
    )
    macro = {
        field: statistics.fmean(
            float(summary[field]) for summary in tier_summaries.values()
        )
        for field in rate_fields
    } if tier_summaries else {}
    return {
        "schema_version": 1,
        "track": "NAV-VERIFIABLE-00",
        "primary_tier": "exploratory",
        "tiers": tier_summaries,
        "overall_equal_tier_macro": macro,
        "pooled_primary_result_prohibited": True,
        "campaign_complete": (
            bool(campaign_manifest.get("complete"))
            if campaign_manifest is not None
            else None
        ),
    }


def _summarize_tier(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(records)

    def rate(mode: str, field: str) -> float:
        return sum(bool(dict(record[mode]).get(field)) for record in records) / count

    outcomes = Counter()
    token_deltas: list[float] = []
    step_deltas: list[float] = []
    for record in records:
        autonomous = dict(record["autonomous"])
        structured = dict(record["structured"])
        autonomous_pass = bool(autonomous.get("exact_correct"))
        structured_pass = bool(structured.get("exact_correct"))
        outcomes[
            (
                "both_pass"
                if autonomous_pass and structured_pass
                else "autonomous_fail_structured_pass"
                if structured_pass
                else "autonomous_pass_structured_fail"
                if autonomous_pass
                else "both_fail"
            )
        ] += 1
        if isinstance(autonomous.get("tokens"), (int, float)) and isinstance(
            structured.get("tokens"), (int, float)
        ):
            token_deltas.append(
                float(structured["tokens"]) - float(autonomous["tokens"])
            )
        if isinstance(autonomous.get("tool_steps"), (int, float)) and isinstance(
            structured.get("tool_steps"), (int, float)
        ):
            step_deltas.append(
                float(structured["tool_steps"])
                - float(autonomous["tool_steps"])
            )
    return {
        "task_count": count,
        "termination_rate_autonomous": rate("autonomous", "completed_with_answer"),
        "termination_rate_structured": rate("structured", "completed_with_answer"),
        "relation_rate_autonomous": rate("autonomous", "relation_correct"),
        "relation_rate_structured": rate("structured", "relation_correct"),
        "evidence_complete_rate_autonomous": rate(
            "autonomous", "evidence_complete"
        ),
        "evidence_complete_rate_structured": rate(
            "structured", "evidence_complete"
        ),
        "evidence_precise_rate_autonomous": rate(
            "autonomous", "evidence_precise"
        ),
        "evidence_precise_rate_structured": rate(
            "structured", "evidence_precise"
        ),
        "exact_rate_autonomous": rate("autonomous", "exact_correct"),
        "exact_rate_structured": rate("structured", "exact_correct"),
        "paired_exact_outcomes": {
            key: outcomes[key]
            for key in (
                "autonomous_fail_structured_pass",
                "autonomous_pass_structured_fail",
                "both_pass",
                "both_fail",
            )
        },
        "median_structured_minus_autonomous_tokens": (
            statistics.median(token_deltas) if token_deltas else None
        ),
        "individual_token_deltas": token_deltas,
        "median_structured_minus_autonomous_tool_steps": (
            statistics.median(step_deltas) if step_deltas else None
        ),
        "individual_tool_step_deltas": step_deltas,
    }


def _sha256_json(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(canonical).hexdigest()
