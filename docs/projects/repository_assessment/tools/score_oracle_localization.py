"""Frozen explicit scorer for the Ornith oracle-localization A/B/C test."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


RESPONSE_FIELDS = ("verdict", "affected_behavior", "actionable_violation", "rationale")


def response_schema(condition: str) -> dict[str, Any]:
    verdicts = ["violation", "no_violation"] if condition == "B" else ["confirm", "reject"]
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": verdicts},
            "affected_behavior": {"type": "string"},
            "actionable_violation": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": list(RESPONSE_FIELDS),
        "additionalProperties": False,
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_response(text: str, condition: str) -> tuple[dict[str, str] | None, str | None]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc.msg}"
    if not isinstance(value, dict) or set(value) != set(RESPONSE_FIELDS):
        return None, "invalid_schema:fields"
    if any(not isinstance(value[field], str) for field in RESPONSE_FIELDS):
        return None, "invalid_schema:types"
    allowed = set(response_schema(condition)["properties"]["verdict"]["enum"])
    if value["verdict"] not in allowed:
        return None, "invalid_schema:verdict"
    return {field: value[field] for field in RESPONSE_FIELDS}, None


def oracle_match(parsed: dict[str, str], oracle: dict[str, Any]) -> tuple[bool, list[bool]]:
    text = "\n".join(parsed[field] for field in RESPONSE_FIELDS[1:]).lower()
    group_matches = [
        any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in group)
        for group in oracle["match_groups"]
    ]
    return all(group_matches), group_matches


def score_response(
    *, condition: str, kind: str, raw_text: str, oracle: dict[str, Any]
) -> dict[str, Any]:
    parsed, error = parse_response(raw_text, condition)
    result: dict[str, Any] = {
        "condition": condition,
        "kind": kind,
        "valid_response": parsed is not None,
        "parse_error": error,
        "verdict": parsed["verdict"] if parsed else None,
        "oracle_match": False,
        "oracle_group_matches": [],
        "localized_recall": False,
        "false_assertion": False,
        "correct_confirmation": False,
        "correct_rejection": False,
        "false_confirmation": False,
        "false_rejection": False,
    }
    if parsed is None:
        return result
    matched, groups = oracle_match(parsed, oracle)
    result["oracle_match"] = matched
    result["oracle_group_matches"] = groups
    if condition == "B":
        result["localized_recall"] = (
            kind == "defect" and parsed["verdict"] == "violation" and matched
        )
        result["false_assertion"] = kind == "negative" and parsed["verdict"] == "violation"
    elif kind == "defect":
        result["correct_confirmation"] = parsed["verdict"] == "confirm" and matched
        result["false_rejection"] = parsed["verdict"] == "reject"
    else:
        result["correct_rejection"] = parsed["verdict"] == "reject"
        result["false_confirmation"] = parsed["verdict"] == "confirm"
    return result


def run_controls(oracles: list[dict[str, Any]]) -> dict[str, Any]:
    oracle = next(row for row in oracles if row["pair_id"] == "tool_state")
    correct = json.dumps(
        {
            "verdict": "violation",
            "affected_behavior": "tool_not_granted error classification",
            "actionable_violation": "The missing blocked classification treats an ungranted tool as a generic failure.",
            "rationale": "The blocked policy set omits tool_not_granted.",
        }
    )
    benign = json.dumps(
        {
            "verdict": "violation",
            "affected_behavior": "dictionary projection",
            "actionable_violation": "The helper returns a compact dictionary.",
            "rationale": "Only named keys are copied.",
        }
    )
    no_violation = json.dumps(
        {
            "verdict": "no_violation",
            "affected_behavior": "tool state classification",
            "actionable_violation": "none",
            "rationale": "The shown code includes the required blocked error.",
        }
    )
    false_assertion = json.dumps(
        {
            "verdict": "violation",
            "affected_behavior": "tool state classification",
            "actionable_violation": "The corrected helper is still unsafe.",
            "rationale": "It allegedly misses a blocked error.",
        }
    )
    rows = [
        {
            "control_id": "accept_correct_identification",
            "expected": {"localized_recall": True},
            "observed": score_response(
                condition="B", kind="defect", raw_text=correct, oracle=oracle
            ),
        },
        {
            "control_id": "reject_description_without_violation",
            "expected": {"localized_recall": False},
            "observed": score_response(
                condition="B", kind="defect", raw_text=benign, oracle=oracle
            ),
        },
        {
            "control_id": "accept_negative_abstention",
            "expected": {"false_assertion": False},
            "observed": score_response(
                condition="B", kind="negative", raw_text=no_violation, oracle=oracle
            ),
        },
        {
            "control_id": "detect_negative_false_assertion",
            "expected": {"false_assertion": True},
            "observed": score_response(
                condition="B", kind="negative", raw_text=false_assertion, oracle=oracle
            ),
        },
    ]
    for row in rows:
        row["passed"] = all(
            row["observed"].get(key) == value for key, value in row["expected"].items()
        )
    return {
        "schema": "oracle-localization-scorer-controls/v1",
        "controls": rows,
        "all_passed": all(row["passed"] for row in rows),
    }


def score_campaign(campaign_root: Path) -> dict[str, Any]:
    spans = load_json(campaign_root / "span-manifest.json")
    oracle_payload = load_json(campaign_root / "oracle-manifest.json")
    matrix = load_json(campaign_root / "run-matrix.json")
    items = {row["item_id"]: row for row in spans["items"]}
    oracles = {row["pair_id"]: row for row in oracle_payload["oracles"]}
    rows: list[dict[str, Any]] = []
    for run in matrix["runs"]:
        item = items[run["item_id"]]
        raw_path = campaign_root / "generations" / run["run_id"] / "raw-response.txt"
        if not raw_path.is_file():
            rows.append({**run, "missing": True})
            continue
        raw = raw_path.read_text(encoding="utf-8")
        rows.append(
            {
                **run,
                "kind": item["kind"],
                "raw_response_sha256": sha256_bytes(raw.encode()),
                **score_response(
                    condition=run["condition"],
                    kind=item["kind"],
                    raw_text=raw,
                    oracle=oracles[item["pair_id"]],
                ),
            }
        )
    summary: dict[str, Any] = {}
    for condition in ("B", "C"):
        selected = [row for row in rows if row["condition"] == condition and not row.get("missing")]
        summary[condition] = {
            "planned": 30,
            "observed": len(selected),
            "valid_responses": sum(bool(row["valid_response"]) for row in selected),
            "localized_recall": sum(bool(row["localized_recall"]) for row in selected),
            "false_assertions": sum(bool(row["false_assertion"]) for row in selected),
            "correct_confirmations": sum(bool(row["correct_confirmation"]) for row in selected),
            "correct_rejections": sum(bool(row["correct_rejection"]) for row in selected),
            "false_confirmations": sum(bool(row["false_confirmation"]) for row in selected),
            "false_rejections": sum(bool(row["false_rejection"]) for row in selected),
        }
    return {
        "schema": "oracle-localization-scores/v1",
        "rows": rows,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--run-controls", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")
    oracle_payload = load_json(args.campaign_root / "oracle-manifest.json")
    result = (
        run_controls(oracle_payload["oracles"])
        if args.run_controls
        else score_campaign(args.campaign_root)
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if result.get("all_passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
