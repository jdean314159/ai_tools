"""
compare_backends.py

Compares eval results from engram vs engram_lite.

Usage:
    python compare_backends.py \
        --engram      eval_results_engram/metrics.json \
        --engram-lite eval_results_lite/metrics.json
"""
import argparse
import json
import math
from pathlib import Path


METRICS_TO_COMPARE = [
    ("recall_direct",            "Recall — Direct query",       "higher"),
    ("recall_paraphrase",        "Recall — Paraphrase query",   "higher"),
    ("recall_decoy",             "Decoy resistance",            "higher"),
    ("contradiction_bleed_rate", "Contradiction bleed rate",    "lower"),
    ("relevance_direct",         "Relevance — Direct",          "higher"),
    ("relevance_paraphrase",     "Relevance — Paraphrase",      "higher"),
]

TRIAL_LABELS = [
    "baseline",
    "reinforce_3x",
    "reinforce_8x",
    "contradict",
    "forgetting",
    "cold_query",
]

DELTA_THRESHOLD = 0.05


def load_metrics(path: str) -> dict:
    return json.loads(Path(path).read_text())


def by_label(metrics: dict) -> dict:
    """Index per_trial list by label."""
    return {t["label"]: t for t in metrics["per_trial"]}


def fmt(v, is_pct=True) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "   n/a "
    if is_pct:
        return f"{v:7.1%}"
    return f"{v:7.3f}"


def delta_marker(e_val, l_val, direction: str) -> str:
    if e_val is None or l_val is None:
        return "   "
    if isinstance(e_val, float) and math.isnan(e_val):
        return "   "
    if isinstance(l_val, float) and math.isnan(l_val):
        return "   "
    diff = l_val - e_val
    if abs(diff) < DELTA_THRESHOLD:
        return " ≈ "
    if direction == "higher":
        return " ▲ " if diff > 0 else " ▼ "
    else:
        return " ▲ " if diff < 0 else " ▼ "


def compare(engram_metrics: dict, lite_metrics: dict):
    e_by = by_label(engram_metrics)
    l_by = by_label(lite_metrics)

    col_w = 9

    print("\n" + "="*100)
    print(f"  {'METRIC / TRIAL':<38} {'ENGRAM':>{col_w}} {'LITE':>{col_w}}  DIR   DELTA")
    print("="*100)

    wins_lite = wins_engram = ties = 0

    for metric_key, metric_label, direction in METRICS_TO_COMPARE:
        print(f"\n  {metric_label}")
        is_pct = metric_key not in ("relevance_direct", "relevance_paraphrase", "relevance_decoy")
        for label in TRIAL_LABELS:
            e_val = e_by.get(label, {}).get(metric_key)
            l_val = l_by.get(label, {}).get(metric_key)
            marker = delta_marker(e_val, l_val, direction)
            diff_str = ""
            if e_val is not None and l_val is not None:
                if not (isinstance(e_val, float) and math.isnan(e_val)):
                    if not (isinstance(l_val, float) and math.isnan(l_val)):
                        diff = l_val - e_val
                        diff_str = f"{diff:+.1%}" if is_pct else f"{diff:+.3f}"
            print(f"    {label:<34} {fmt(e_val, is_pct):>{col_w}} {fmt(l_val, is_pct):>{col_w}}  "
                  f"{marker}  {diff_str}")
            if marker.strip() == "▲":
                wins_lite += 1
            elif marker.strip() == "▼":
                wins_engram += 1
            elif marker.strip() == "≈":
                ties += 1

    # RTRL novelty — engram only
    print(f"\n  RTRL Novelty mean (engram only — N/A in engram_lite)")
    for label in TRIAL_LABELS:
        e_val = e_by.get(label, {}).get("novelty_mean")
        e_str = f"{e_val:.4f}" if e_val is not None else "    n/a"
        print(f"    {label:<34} {e_str:>{col_w}}")

    # Latency
    print(f"\n  Elapsed seconds per trial")
    for label in TRIAL_LABELS:
        e_sec = e_by.get(label, {}).get("elapsed_sec")
        l_sec = l_by.get(label, {}).get("elapsed_sec")
        e_str = f"{e_sec:.1f}s" if e_sec is not None else "n/a"
        l_str = f"{l_sec:.1f}s" if l_sec is not None else "n/a"
        print(f"    {label:<34} {e_str:>{col_w}} {l_str:>{col_w}}")

    # Summary
    total = wins_lite + wins_engram + ties
    print("\n" + "="*100)
    print("  SUMMARY")
    print("="*100)
    print("  ▲ = engram_lite better   ▼ = engram better   ≈ = within 5pp")
    print()
    print(f"  engram_lite better : {wins_lite}/{total}")
    print(f"  engram better      : {wins_engram}/{total}")
    print(f"  Within 5pp         : {ties}/{total}")
    print("="*100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engram",      required=True)
    parser.add_argument("--engram-lite", required=True, dest="lite")
    args = parser.parse_args()
    compare(load_metrics(args.engram), load_metrics(args.lite))


if __name__ == "__main__":
    main()