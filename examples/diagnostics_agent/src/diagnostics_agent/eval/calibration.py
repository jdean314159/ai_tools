from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from diagnostics_agent.interpret import Interpretation, _RISK_RANK
from diagnostics_agent.triage import TriageSummary


_BAND_RANK = {
    "excluded": _RISK_RANK["none"],
    "low": _RISK_RANK["low"],
    "medium": _RISK_RANK["medium"],
    "high": _RISK_RANK["high"],
}
_SEVERITY_TO_BAND = {
    "info": "excluded",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "high",
}


@dataclass(frozen=True)
class ConcernScore:
    finding_ref: str
    expected_band: str
    actual_severity: str | None
    outcome: str
    band_delta: int
    known_gap: bool


@dataclass(frozen=True)
class CaseScore:
    case: str
    concern_scores: tuple[ConcernScore, ...]
    unexpected_concerns: tuple[str, ...]
    overall_security_ok: bool
    overall_operational_ok: bool


@dataclass(frozen=True)
class EvalReport:
    case_scores: tuple[CaseScore, ...]
    fp_rate: float | None
    recall: float | None
    band_accuracy: float | None
    counts: dict[str, int]


def score_case(
    interpretation: Interpretation | None,
    summary: TriageSummary,
    labels: dict,
) -> CaseScore:
    del summary  # Reserved for future triage-aware scoring.
    expected = labels.get("expected_concerns", [])
    expected_refs = {item["finding_ref"] for item in expected}
    actual_by_ref = _actual_concerns_by_ref(interpretation)

    concern_scores = tuple(
        _score_concern(
            finding_ref=item["finding_ref"],
            expected_band=item["expected_band"],
            actual_severity=actual_by_ref.get(item["finding_ref"]),
            known_gap=bool(item.get("known_gap", False)),
        )
        for item in expected
    )
    unexpected = tuple(sorted(set(actual_by_ref) - expected_refs))
    expected_overall = labels.get("expected_overall", {})

    return CaseScore(
        case=labels["case"],
        concern_scores=concern_scores,
        unexpected_concerns=unexpected,
        overall_security_ok=_overall_matches(
            interpretation,
            "security_risk",
            expected_overall.get("security_risk"),
        ),
        overall_operational_ok=_overall_matches(
            interpretation,
            "operational_risk",
            expected_overall.get("operational_risk"),
        ),
    )


def aggregate(case_scores: Sequence[CaseScore]) -> EvalReport:
    counts: Counter[str] = Counter()
    excluded_total = 0
    non_excluded_total = 0
    produced_non_excluded = 0
    false_positives = 0
    recalled = 0
    band_correct = 0

    for case_score in case_scores:
        for concern in case_score.concern_scores:
            if concern.known_gap:
                continue
            counts[concern.outcome] += 1
            if concern.expected_band == "excluded":
                excluded_total += 1
                if concern.outcome == "false_positive":
                    false_positives += 1
                continue

            non_excluded_total += 1
            if concern.outcome in {"ok", "miscalibrated"}:
                produced_non_excluded += 1
                recalled += 1
                if concern.outcome == "ok":
                    band_correct += 1

        unexpected_count = len(case_score.unexpected_concerns)
        if unexpected_count:
            false_positives += unexpected_count
            excluded_total += unexpected_count
            counts["false_positive"] += unexpected_count
            counts["unexpected_concern"] += unexpected_count

    return EvalReport(
        case_scores=tuple(case_scores),
        fp_rate=false_positives / excluded_total if excluded_total else None,
        recall=recalled / non_excluded_total if non_excluded_total else None,
        band_accuracy=(
            band_correct / produced_non_excluded if produced_non_excluded else None
        ),
        counts=dict(sorted(counts.items())),
    )


def _actual_concerns_by_ref(
    interpretation: Interpretation | None,
) -> dict[str, str]:
    if interpretation is None:
        return {}

    actual: dict[str, str] = {}
    for concern in interpretation.prioritized_concerns:
        previous = actual.get(concern.finding_ref)
        if previous is None or _severity_rank(concern.severity) > _severity_rank(previous):
            actual[concern.finding_ref] = concern.severity
    return actual


def _score_concern(
    *,
    finding_ref: str,
    expected_band: str,
    actual_severity: str | None,
    known_gap: bool,
) -> ConcernScore:
    if expected_band not in _BAND_RANK:
        raise ValueError(f"unsupported expected band: {expected_band}")

    if actual_severity is None:
        outcome = "ok" if expected_band == "excluded" else "miss"
        delta = 0 if expected_band == "excluded" else -_BAND_RANK[expected_band]
    else:
        actual_band = _SEVERITY_TO_BAND[actual_severity]
        delta = _BAND_RANK[actual_band] - _BAND_RANK[expected_band]
        if expected_band == "excluded":
            outcome = "false_positive"
        elif actual_band == expected_band:
            outcome = "ok"
        else:
            outcome = "miscalibrated"

    return ConcernScore(
        finding_ref=finding_ref,
        expected_band=expected_band,
        actual_severity=actual_severity,
        outcome=outcome,
        band_delta=delta,
        known_gap=known_gap,
    )


def _overall_matches(
    interpretation: Interpretation | None,
    field_name: str,
    expected: str | None,
) -> bool:
    if expected is None:
        return True
    if interpretation is None:
        return False
    return getattr(interpretation, field_name) == expected


def _severity_rank(severity: str) -> int:
    return _BAND_RANK[_SEVERITY_TO_BAND[severity]]
