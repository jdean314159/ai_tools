from __future__ import annotations

import json

from diagnostics_agent.eval.calibration import EvalReport


def render_report(report: EvalReport, errors: dict[str, str]) -> str:
    lines = [
        "Diagnostics severity calibration report",
        "",
        f"{'case':24} {'finding_ref':28} {'expected':10} {'actual':10} outcome",
        "-" * 92,
    ]
    known_gaps = []
    for case in report.case_scores:
        for concern in case.concern_scores:
            row = (case.case, concern)
            if concern.known_gap:
                known_gaps.append(row)
                continue
            lines.append(
                f"{case.case:24} {concern.finding_ref:28} "
                f"{concern.expected_band:10} {(concern.actual_severity or '-'):10} "
                f"{concern.outcome}"
            )
        for finding_ref in case.unexpected_concerns:
            lines.append(
                f"{case.case:24} {finding_ref:28} "
                f"{'excluded':10} {'emitted':10} false_positive (unexpected)"
            )
        if case.case in errors:
            lines.append(
                f"{case.case:24} {'<interpretation>':28} {'-':10} {'-':10} "
                f"ERROR: {errors[case.case]}"
            )

    lines.extend(
        [
            "",
            "Aggregate metrics (known gaps excluded)",
            f"fp_rate:       {_format_metric(report.fp_rate)}",
            f"recall:        {_format_metric(report.recall)}",
            f"band_accuracy: {_format_metric(report.band_accuracy)}",
            f"counts:        {json.dumps(report.counts, sort_keys=True)}",
        ]
    )

    if known_gaps:
        lines.extend(
            [
                "",
                "Known gaps (reported, excluded from aggregate metrics)",
            ]
        )
        for case_name, concern in known_gaps:
            lines.append(
                f"{case_name}: {concern.finding_ref} expected={concern.expected_band} "
                f"actual={concern.actual_severity or '-'} outcome={concern.outcome}"
            )

    return "\n".join(lines)


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"
