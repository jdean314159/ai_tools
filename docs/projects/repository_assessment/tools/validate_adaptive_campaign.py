"""Independently validate retained adaptive repository-assessment artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
from typing import Any


_RUNNER_PATH = Path(__file__).with_name("run_adaptive_staged_assessment.py")
_SPEC = importlib.util.spec_from_file_location("adaptive_campaign_validator_runner", _RUNNER_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - import invariant
    raise RuntimeError(f"cannot load adaptive harness: {_RUNNER_PATH}")
runner = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault(_SPEC.name, runner)
_SPEC.loader.exec_module(runner)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _evidence_resolves(
    record: dict[str, Any], stage_id: str, tool_events: list[dict[str, Any]]
) -> bool:
    for prefix in ("contract", "behavior", "disconfirmation"):
        evidence_id = record[f"{prefix}_call_id"]
        quote = record[f"{prefix}_quote"].strip()
        matches = [
            event
            for event in tool_events
            if event.get("stage_id") == stage_id and event.get("evidence_id") == evidence_id
        ]
        if len(matches) != 1:
            return False
        result = matches[0]["result"]
        output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
        if quote not in output:
            return False
    return True


def audit_v2(run_dir: Path, target: Path) -> dict[str, Any]:
    metadata = _load(run_dir / "run-metadata.json")
    events = _events(run_dir / "transcript.jsonl")
    tool_events = [
        event
        for event in events
        if event.get("event") == "tool"
        and event.get("tool") == "shell"
        and event.get("evidence_id")
    ]
    scout_calls = sum(event.get("stage") == "scout" for event in tool_events)
    verifier_calls = sum(event.get("stage") == "verifier" for event in tool_events)

    dossier_checks = []
    for scope, expected_hash in metadata["dossiers"]["sha256"].items():
        retained = run_dir / "dossiers" / f"{scope}.json"
        regenerated = runner.canonical_dossier_bytes(runner.build_package_dossier(target, scope))
        dossier_checks.append(
            _sha256(retained) == expected_hash
            and retained.read_bytes() == regenerated
            and hashlib.sha256(regenerated).hexdigest() == expected_hash
        )

    traces_by_stage: dict[str, Any] = {}
    for event in tool_events:
        stage_id = event["stage_id"]
        scope = stage_id.rsplit(":", 1)[-1]
        trace = traces_by_stage.setdefault(stage_id, runner.StageTrace(stage_id, scope))
        trace.calls.append(
            {
                "evidence_id": event["evidence_id"],
                "tool_call_id": event["tool_call_id"],
                "command": event["result"]["command"],
                "result": event["result"],
            }
        )
    recomputed_coverage = runner._coverage_snapshot(list(traces_by_stage.values()))

    evidence_checks = []
    for record in metadata["scouts"]["results"]:
        if record.get("evidence_validation", {}).get("valid"):
            evidence_checks.append(
                _evidence_resolves(record, f"scout:{record['scope']}", tool_events)
            )
    for index, record in enumerate(metadata["verifiers"]["results"], 1):
        if record.get("evidence_validation", {}).get("valid"):
            stage_id = f"verifier:{index}:{record['scope']}"
            evidence_checks.append(_evidence_resolves(record, stage_id, tool_events))

    rendered = runner.render_authoritative_report(
        accepted=metadata["accepted_findings"],
        verifications=metadata["verifiers"]["results"],
        coverage=metadata["substantive_coverage"],
        uncertainty=metadata["remaining_uncertainty"],
    ).encode()
    report_path = run_dir / "raw-controller-report.md"
    report_matches = rendered == report_path.read_bytes()
    transcript_hash_matches = _sha256(run_dir / "transcript.jsonl") == metadata["transcript_sha256"]
    report_hash_matches = _sha256(report_path) == metadata["report_sha256"]

    gates = {
        "dossiers": len(dossier_checks) == 9 and all(dossier_checks),
        "selections": metadata["selections"]["valid"] == 9,
        "evidence": all(evidence_checks),
        "budgets": scout_calls <= 18
        and verifier_calls <= 27
        and len(tool_events) <= 45
        and len(tool_events) == metadata["shell_tool_calls"],
        "verifiers": metadata["verifiers"]["structured"] == metadata["promotion"]["selected"],
        "report": report_matches and report_hash_matches and transcript_hash_matches,
        "coverage": recomputed_coverage == metadata["substantive_coverage"],
    }
    return {
        "seed": metadata["seed"],
        "condition": metadata["condition"],
        "lifecycle": metadata["lifecycle"],
        "completion_mode": metadata["completion_mode"],
        "mechanical_gates": gates,
        "mechanical_pass": all(gates.values()),
        "shell_calls": len(tool_events),
        "scout_calls": scout_calls,
        "verifier_calls": verifier_calls,
        "coverage": metadata["substantive_coverage"]["covered"],
        "max_scope_concentration": metadata["max_scope_concentration"],
        "input_tokens": metadata["usage"]["input_tokens"],
        "output_tokens": metadata["usage"]["output_tokens"],
        "model_calls": metadata["usage"]["model_calls"],
        "promoted": metadata["promotion"]["selected"],
        "accepted_findings": len(metadata["accepted_findings"]),
        "valid_evidence_records_rechecked": len(evidence_checks),
        "invalid_evidence_records": sum(
            record.get("evidence_validation", {}).get("valid") is False
            for record in [*metadata["scouts"]["results"], *metadata["verifiers"]["results"]]
        ),
        "binding_mismatches": sum(
            record.get("selection_binding", {}).get("valid") is False
            for record in [*metadata["scouts"]["results"], *metadata["verifiers"]["results"]]
        ),
        "protocol_violations": metadata["protocol_violations"],
    }


def audit_v1(run_dir: Path) -> dict[str, Any]:
    metadata = _load(run_dir / "run-metadata.json")
    traces = {scope: runner.v1.ScopeTrace(scope) for scope in runner.PACKAGE_NAMES}
    for event in _events(run_dir / "transcript.jsonl"):
        if event.get("event") != "tool" or event.get("tool") != "shell":
            continue
        result = event.get("result", {})
        if "returncode" not in result:
            continue
        scope = event["stage_id"].rsplit(":", 1)[-1]
        traces[scope].commands.append({"command": result["command"], "result": result})
    scopes = {scope: trace.coverage() for scope, trace in traces.items()}
    recomputed_coverage = {
        "covered": sum(item["covered"] for item in scopes.values()),
        "scopes": scopes,
    }
    return {
        "seed": metadata["seed"],
        "condition": metadata["condition"],
        "lifecycle": metadata["lifecycle"],
        "completion_mode": metadata["completion_mode"],
        "artifact_hashes_match": (
            _sha256(run_dir / "transcript.jsonl") == metadata["transcript_sha256"]
            and _sha256(run_dir / "raw-model-report.md") == metadata["report_sha256"]
        ),
        "coverage_recomputed_matches": recomputed_coverage == metadata["substantive_coverage"],
        "structured_scouts": metadata["scouts"]["structured"],
        "structured_verifiers": metadata["verifiers"]["structured"],
        "shell_calls": metadata["shell_tool_calls"],
        "coverage": metadata["substantive_coverage"]["covered"],
        "max_scope_concentration": metadata["max_scope_concentration"],
        "input_tokens": metadata["usage"]["input_tokens"],
        "output_tokens": metadata["usage"]["output_tokens"],
        "model_calls": metadata["usage"]["model_calls"],
        "promoted": metadata["candidate_selection"]["selected"],
        "accepted_findings": len(metadata["accepted_findings"]),
        "protocol_violations": metadata["protocol_violations"],
    }


def _medians(records: list[dict[str, Any]]) -> dict[str, float]:
    fields = ("shell_calls", "coverage", "max_scope_concentration", "input_tokens")
    return {field: statistics.median(record[field] for record in records) for field in fields}


def validate_campaign(campaign: Path, target: Path, grader_result: Path) -> dict[str, Any]:
    metadata_paths = sorted(campaign.glob("pair-seed*/*/run-metadata.json"))
    v1_records = []
    v2_records = []
    for path in metadata_paths:
        metadata = _load(path)
        if metadata["condition"] == runner.CONDITION:
            v2_records.append(audit_v2(path.parent, target))
        else:
            v1_records.append(audit_v1(path.parent))
    v1_records.sort(key=lambda record: record["seed"])
    v2_records.sort(key=lambda record: record["seed"])

    snapshots = sorted(campaign.glob("pair-seed*/endpoint-*.json"))
    snapshot_records = [_load(path) for path in snapshots]
    endpoint_hashes = {record["fingerprint_sha256"] for record in snapshot_records}
    endpoints_stable = (
        len(snapshot_records) == 6
        and len(endpoint_hashes) == 1
        and all(record["health"] == "ok" for record in snapshot_records)
    )
    grader = _load(grader_result)
    grader_pass = grader["target"]["failed"] == 3 and grader["head"]["passed"] == 3
    all_v2_mechanical = len(v2_records) == 3 and all(
        record["mechanical_pass"] and record["lifecycle"] == "final" for record in v2_records
    )
    return {
        "schema": "temporary-adaptive-campaign-validation/v1",
        "campaign": campaign.name,
        "runs_found": len(metadata_paths),
        "endpoint": {
            "snapshots": len(snapshot_records),
            "stable": endpoints_stable,
            "fingerprint_sha256": next(iter(endpoint_hashes))
            if len(endpoint_hashes) == 1
            else None,
        },
        "grader_pass": grader_pass,
        "all_v2_mechanical_gates_pass": all_v2_mechanical and grader_pass and endpoints_stable,
        "v1": {"runs": v1_records, "medians": _medians(v1_records)},
        "v2_2": {"runs": v2_records, "medians": _medians(v2_records)},
        "known_defect_recall": {
            "v1": {str(record["seed"]): "0/3" for record in v1_records},
            "v2_2": {str(record["seed"]): "0/3" for record in v2_records},
            "basis": "No authoritative report contained an accepted finding.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--grader-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")
    result = validate_campaign(args.campaign, args.target, args.grader_result)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_v2_mechanical_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
