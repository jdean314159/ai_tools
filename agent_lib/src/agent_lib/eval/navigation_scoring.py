from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from ..contracts import AgentRun
from .navigation_claims import NavigationClaim, validate_navigation_claims
from .navigation_ground_truth import GroundTruthRegion
from .navigation_planner import NavigationBudget
from .navigation_workspace import NavigationTelemetry


def score_navigation_run(
    run: AgentRun,
    telemetry: NavigationTelemetry,
    regions: Sequence[GroundTruthRegion],
    budget: NavigationBudget,
    *,
    max_steps: int = 25,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    surfaced: set[str] = set()
    useful_calls = 0
    successful_calls = 0
    for call in telemetry.calls:
        call_useful = False
        if call["success"]:
            successful_calls += 1
        for evidence in call.get("evidence") or []:
            evidence_lines = set(int(line) for line in evidence.get("lines") or [])
            for region in regions:
                if evidence.get("path") == region.path and evidence_lines.intersection(
                    range(region.start_line, region.end_line + 1)
                ):
                    surfaced.add(region.id)
                    call_useful = True
        if call_useful:
            useful_calls += 1
    raw_claims = run.meta.get("navigation_claims")
    if raw_claims is None and run.steps:
        raw_claims = run.steps[-1].action.meta.get("navigation_claims")
    claim_parse_errors: list[str] = []
    claims: list[NavigationClaim] = []
    if isinstance(raw_claims, list):
        for index, item in enumerate(raw_claims, start=1):
            if not isinstance(item, Mapping):
                claim_parse_errors.append(f"claim {index} is not an object")
                continue
            try:
                claims.append(NavigationClaim.from_mapping(item))
            except (TypeError, ValueError) as exc:
                claim_parse_errors.append(f"claim {index} is invalid: {exc}")
    else:
        claim_parse_errors.append("missing structured navigation claims")
    claim_validation = validate_navigation_claims(
        claims,
        telemetry_calls=telemetry.calls,
        regions=regions,
        source_root=source_root,
    )
    correctly_named = set(claim_validation.matched_region_ids)
    known_paths = {region.path for region in regions}
    false_positive_paths = sorted(
        {
            str(claim.get("path") or "")
            for claim in claim_validation.unsupported_claims
            if claim.get("path") and claim.get("path") not in known_paths
        }
    )
    claim_errors = [*claim_parse_errors, *claim_validation.errors]
    blocked = [
        call
        for call in telemetry.calls
        if call["category"]
        in {
            "path_escape",
            "denied_path",
            "denied_content",
            "oversized_json",
            "oversized_file",
            "binary_content",
            "safety_guard",
        }
    ]
    blocked_signatures = [
        (call["tool"], json.dumps(call["arguments"], sort_keys=True)) for call in blocked
    ]
    repeated_blocked = len(blocked_signatures) - len(set(blocked_signatures))
    usage = dict(run.meta.get("planner_usage") or {})
    cumulative_tokens = int(usage.get("cumulative_actual_tokens") or 0)
    evidence_recall = len(surfaced) / len(regions) if regions else 0.0
    answer_correctness = len(correctly_named) / len(regions) if regions else 0.0
    passed = (
        evidence_recall == 1.0
        and answer_correctness == 1.0
        and not false_positive_paths
        and not claim_validation.unsupported_claims
        and not claim_errors
        and telemetry.denied_content_bytes == 0
        and len(blocked) <= 3
        and repeated_blocked == 0
        and cumulative_tokens <= budget.cumulative_token_limit
        and len(run.steps) <= max_steps
        and run.status == "completed"
    )
    return {
        "passed": passed,
        "evidence_recall": evidence_recall,
        "surfaced_region_ids": sorted(surfaced),
        "answer_correctness": answer_correctness,
        "correct_region_ids": sorted(correctly_named),
        "answer_scoring_mode": "structured_claims",
        "missing_region_ids": list(claim_validation.missing_region_ids),
        "unsupported_claims": list(claim_validation.unsupported_claims),
        "claim_validation_errors": claim_errors,
        "false_positive_paths": false_positive_paths,
        "denied_content_bytes": telemetry.denied_content_bytes,
        "blocked_attempts": len(blocked),
        "repeated_blocked_attempts": repeated_blocked,
        "automatic_pruned_paths": telemetry.automatic_pruned_paths,
        "useful_call_rate": useful_calls / successful_calls if successful_calls else 0.0,
        "tool_calls": len(telemetry.calls),
        "cumulative_tokens": cumulative_tokens,
        "steps": len(run.steps),
        "stop_reason": run.stop_reason,
    }
