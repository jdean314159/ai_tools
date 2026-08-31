#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _summary_lines(title: str, summary: dict) -> list[str]:
    lines = [title]
    ordered_keys = [
        "probe_pass_rate",
        "raw_probe_pass_rate",
        "prompt_pass_rate",
        "answer_uplift_rate",
        "answer_support_rate",
        "answer_correct_rate",
        "baseline_answer_correct_rate",
        "memory_answer_correct_rate",
        "signal_retention_rate",
        "paraphrase_retention_rate",
        "decoy_rejection_rate",
        "update_resolution_rate",
        "noise_rejection_rate",
        "avg_redundancy_ratio",
    ]
    for key in ordered_keys:
        if key in summary:
            lines.append(f"  {key}: {summary[key]}")
    if "failed_probes" in summary:
        lines.append(
            f"  failed_probes: {', '.join(summary['failed_probes']) if summary['failed_probes'] else 'none'}"
        )
    if "failed_raw_probes" in summary:
        lines.append(
            f"  failed_raw_probes: {', '.join(summary['failed_raw_probes']) if summary['failed_raw_probes'] else 'none'}"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize ai_tools answer-uplift memory evaluation results."
    )
    parser.add_argument("report_json", help="Path to memory_eval JSON report.")
    args = parser.parse_args()

    report = json.loads(Path(args.report_json).read_text(encoding="utf-8"))

    if "results" in report:
        print("Per-scenario summary")
        for scenario_name, scenario_data in report["results"].items():
            print(f"\n{scenario_name}")
            backends = scenario_data.get("backends", {})
            for backend, backend_data in backends.items():
                summary = backend_data.get("summary", {})
                for line in _summary_lines(f"{backend}", summary):
                    print(line)
    if "aggregate" in report:
        print("\nAggregate summary")
        for backend, summary in report["aggregate"].items():
            for line in _summary_lines(f"{backend}", summary):
                print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
