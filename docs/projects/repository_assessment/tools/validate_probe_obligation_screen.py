"""Validate the frozen two-run Ornith empirical-probe-obligation screen."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


_TOOLS_DIR = Path(__file__).resolve().parent


def _load_sibling(module_name: str, filename: str) -> Any:
    path = _TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import invariant
        raise RuntimeError(f"cannot load maintained assessment helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


runner = _load_sibling("probe_screen_runner", "run_probe_obligation_screen.py")
transfer_validator = _load_sibling(
    "probe_screen_transfer_validator", "validate_model_blind_transfer_pilot.py"
)


RUNS = (
    ("01-probe-optional-seed31", "probe_optional"),
    ("02-probe-required-seed31", "probe_required"),
)
VALID_COMPLETION_MODES = {
    "natural",
    "forced",
    "structural_noncompletion",
    "forced_invalid",
}
VALID_OUTCOMES = {
    "natural_valid_submission",
    "natural_after_gate_block",
    "forced_valid_submission",
    "structural_noncompletion_probe_unsatisfied",
    "forced_invalid_submission",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _archive_commit(path: Path) -> str | None:
    with path.open("rb") as handle:
        proc = subprocess.run(
            ["git", "get-tar-commit-id"],
            stdin=handle,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    return proc.stdout.strip() if proc.returncode == 0 else None


def run_gate_controls(*, root: Path, venv: Path, rg_path: Path) -> dict[str, Any]:
    """Exercise one rejecting and one accepting probe through the real sandbox."""
    negative = runner.run_instrumented_probe(
        root=root,
        venv=venv,
        rg_path=rg_path,
        call_id="negative-control-no-repository-import",
        filename="negative_control.py",
        code='print("negative control observation")\n',
    )
    positive = runner.run_instrumented_probe(
        root=root,
        venv=venv,
        rg_path=rg_path,
        call_id="positive-control-repository-import",
        filename="positive_control.py",
        code=(
            "import llm_harness_core\n"
            'print("positive control origin:", llm_harness_core.__file__)\n'
        ),
    )
    negative_valid = (
        negative.get("satisfied") is False
        and "no_workspace_module_loaded" in negative.get("satisfaction_failures", [])
        and negative.get("observed_output_present") is True
    )
    positive_valid = (
        positive.get("satisfied") is True
        and positive.get("observed_output_present") is True
        and any(
            isinstance(path, str) and path.startswith("/workspace/")
            for path in positive.get("workspace_module_files", [])
        )
    )
    return {
        "schema": "temporary-probe-obligation-gate-controls/v1",
        "valid": negative_valid and positive_valid,
        "proposition": (
            "The gate rejects an executed, output-producing script that loads no module from "
            "/workspace and accepts one that does."
        ),
        "negative_control": negative,
        "negative_control_valid": negative_valid,
        "positive_control": positive,
        "positive_control_valid": positive_valid,
    }


def validate_preflight(
    *,
    manifest_path: Path,
    source_root: Path,
    archive_path: Path,
    target_root: Path,
    venv: Path,
    rg_path: Path,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    errors: list[str] = []
    reference_fingerprint = Path(manifest["reference_fingerprint_path"])
    if not reference_fingerprint.is_absolute():
        reference_fingerprint = source_root.parents[2] / reference_fingerprint
    expected_files = {
        "runner_sha256": source_root / "tools" / "run_probe_obligation_screen.py",
        "validator_sha256": source_root / "tools" / "validate_probe_obligation_screen.py",
        "grader_sha256": source_root / "tools" / "test_engram_boundary_defects_at_7d37920.py",
        "reference_fingerprint_sha256": reference_fingerprint,
    }
    for field, path in expected_files.items():
        if not path.is_file():
            errors.append(f"missing frozen file for {field}: {path}")
        elif manifest.get(field) != _sha256(path):
            errors.append(f"{field} mismatch")

    runtime_values = {
        "prompt_sha256": {
            "shared_system": runner.base.sha256_bytes(runner.SHARED_SYSTEM_PROMPT.encode("utf-8")),
            "shared_user": runner.base.sha256_bytes(runner.SHARED_USER_PROMPT.encode("utf-8")),
            "probe_obligation": runner.base.sha256_bytes(
                runner.PROBE_OBLIGATION_PROMPT.encode("utf-8")
            ),
        },
        "tool_schema_sha256": {
            "shell": runner.tool_schema_sha256(runner.base.SHELL_TOOL),
            "run_probe": runner.tool_schema_sha256(runner.RUN_PROBE_TOOL),
            "submit_report": runner.tool_schema_sha256(runner.SCREEN_REPORT_TOOL),
        },
        "controller_policy_sha256": runner._canonical_sha256(runner.controller_policy()),
    }
    for field, value in runtime_values.items():
        if manifest.get(field) != value:
            errors.append(f"{field} mismatch")
    if runner.treatment_language_violations():
        errors.append("treatment-only model-visible text contains forbidden target terms")
    if manifest.get("generated_before_first_model_request") is not True:
        errors.append("manifest does not assert pre-generation freeze ordering")
    if manifest.get("protocol_status") != "frozen":
        errors.append("protocol is not frozen")
    if manifest.get("target_identity") != runner.TARGET_IDENTITY:
        errors.append("target identity mismatch")
    if not archive_path.is_file():
        errors.append("target archive is missing")
    else:
        if _sha256(archive_path) != runner.TARGET_IDENTITY["target_archive_sha256"]:
            errors.append("target archive digest mismatch")
        if _archive_commit(archive_path) != runner.TARGET_IDENTITY["target_commit"]:
            errors.append("target archive embedded commit mismatch")

    sandbox = runner.staged.validate_sanitized_sandbox(target_root, venv, rg_path)
    if not sandbox.get("valid"):
        errors.append("sanitized sandbox validation failed")
    gate_controls = run_gate_controls(root=target_root, venv=venv, rg_path=rg_path)
    if not gate_controls["valid"]:
        errors.append("probe gate controls failed")
    return {
        "schema": "temporary-probe-obligation-screen-preflight/v1",
        "valid": not errors,
        "errors": errors,
        "manifest_sha256": _sha256(manifest_path),
        "archive_sha256": _sha256(archive_path) if archive_path.is_file() else None,
        "archive_embedded_commit": (
            _archive_commit(archive_path) if archive_path.is_file() else None
        ),
        "sandbox": sandbox,
        "gate_controls": gate_controls,
        "recall_adjudicated": False,
        "grader_executed": False,
    }


def _validate_run(*, run_dir: Path, condition: str, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata_path = run_dir / "run-metadata.json"
    if not metadata_path.is_file():
        return [f"{run_dir.name}: missing run metadata"]
    metadata = _read_json(metadata_path)
    expected = {
        "schema": "temporary-repository-assessment-probe-obligation-screen-run/v1",
        "condition": condition,
        "seed": runner.SEED,
        "model": runner.MODEL_LABEL,
        **runner.TARGET_IDENTITY,
        "action_call_budget": runner.ACTION_CALL_BUDGET,
        "model_turn_ceiling": runner.MODEL_TURN_CEILING,
        "prompt_sha256": manifest["prompt_sha256"],
        "tool_schema_sha256": manifest["tool_schema_sha256"],
        "controller_policy_sha256": manifest["controller_policy_sha256"],
        "runner_sha256": manifest["runner_sha256"],
        "treatment_language_violations": [],
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            errors.append(f"{run_dir.name}: {field} mismatch")
    if metadata.get("action_calls", runner.ACTION_CALL_BUDGET + 1) > runner.ACTION_CALL_BUDGET:
        errors.append(f"{run_dir.name}: action budget exceeded")
    if metadata.get("completion_mode") not in VALID_COMPLETION_MODES:
        errors.append(f"{run_dir.name}: unknown completion mode")
    if metadata.get("outcome") not in VALID_OUTCOMES:
        errors.append(f"{run_dir.name}: unknown outcome")
    if condition == "probe_required":
        completion = metadata.get("completion_mode")
        satisfying = metadata.get("satisfying_probe_calls", 0)
        if completion in {"natural", "forced"} and satisfying < 1:
            errors.append(f"{run_dir.name}: completed treatment without satisfying probe")
        if completion == "structural_noncompletion" and satisfying != 0:
            errors.append(f"{run_dir.name}: structural noncompletion has satisfying probe")
    transcript = run_dir / "transcript.jsonl"
    report = run_dir / "raw-model-report.md"
    for path, field in ((transcript, "transcript_sha256"), (report, "report_sha256")):
        if not path.is_file():
            errors.append(f"{run_dir.name}: missing {path.name}")
        elif metadata.get(field) != _sha256(path):
            errors.append(f"{run_dir.name}: {field} mismatch")
    return errors


def _validate_grader_results(path: Path, grader_sha256: str) -> list[str]:
    if not path.is_file():
        return ["missing external grader results"]
    value = _read_json(path)
    expected = {
        "grader_sha256": grader_sha256,
        "target_commit": runner.TARGET_IDENTITY["target_commit"],
        "corrected_reference": "8e2e9e5f2c45c935bdc3afa2479a08dc702b44db",
        "target_result": {"failed": 3, "passed": 0, "returncode": 1},
        "corrected_reference_result": {"failed": 0, "passed": 3, "returncode": 0},
    }
    return [
        f"external grader {field} mismatch"
        for field, expected_value in expected.items()
        if value.get(field) != expected_value
    ]


def _validate_adjudication(path: Path) -> tuple[list[str], dict[str, Any] | None]:
    if not path.is_file():
        return ["missing post-run adjudication"], None
    value = _read_json(path)
    errors: list[str] = []
    if value.get("independent_verification") is not False:
        errors.append("adjudication must disclose that it is not independently verified")
    runs = value.get("runs")
    if not isinstance(runs, dict):
        return [*errors, "adjudication runs must be an object"], value
    for run_name, condition in RUNS:
        record = runs.get(condition)
        if not isinstance(record, dict):
            errors.append(f"adjudication missing {condition}")
            continue
        if record.get("run_directory") != run_name:
            errors.append(f"adjudication {condition} run directory mismatch")
        if record.get("valid_defect_denominator") != 3:
            errors.append(f"adjudication {condition} denominator mismatch")
        recalled = record.get("recalled_defects")
        if not isinstance(recalled, list) or record.get("recall_count") != len(recalled):
            errors.append(f"adjudication {condition} recall count mismatch")
        false_positives = record.get("accepted_false_positives")
        if not isinstance(false_positives, list):
            errors.append(f"adjudication {condition} false positives must be a list")
    return errors, value


def validate_campaign(*, campaign_root: Path, source_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = campaign_root / "freeze-manifest.json"
    if not manifest_path.is_file():
        return {
            "schema": "temporary-probe-obligation-screen-validation/v1",
            "valid": False,
            "errors": ["missing freeze manifest"],
            "recall_adjudicated": False,
        }
    manifest = _read_json(manifest_path)
    frozen_files = {
        "runner_sha256": source_root / "tools" / "run_probe_obligation_screen.py",
        "validator_sha256": source_root / "tools" / "validate_probe_obligation_screen.py",
        "grader_sha256": source_root / "tools" / "test_engram_boundary_defects_at_7d37920.py",
    }
    for field, path in frozen_files.items():
        if not path.is_file() or _sha256(path) != manifest.get(field):
            errors.append(f"{field} mismatch")
    preflight_path = campaign_root / "preflight-validation.json"
    if not preflight_path.is_file() or _read_json(preflight_path).get("valid") is not True:
        errors.append("missing or invalid preflight validation")
    for run_name, condition in RUNS:
        errors.extend(
            _validate_run(
                run_dir=campaign_root / run_name,
                condition=condition,
                manifest=manifest,
            )
        )

    before_path = campaign_root / "endpoint-before.json"
    after_path = campaign_root / "endpoint-after.json"
    endpoint_observations: list[str] = []
    if not before_path.is_file() or not after_path.is_file():
        errors.append("missing endpoint before/after snapshots")
    else:
        before = _read_json(before_path)
        after = _read_json(after_path)
        endpoint_errors, endpoint_observations = transfer_validator.compare_endpoint_snapshots(
            before, after
        )
        errors.extend(endpoint_errors)
        if before.get("health") != "ok" or after.get("health") != "ok":
            errors.append("endpoint health was not ok")

    errors.extend(
        _validate_grader_results(
            campaign_root / "external-grader-results.json", manifest["grader_sha256"]
        )
    )
    adjudication_errors, adjudication = _validate_adjudication(
        campaign_root / "post-run-adjudication.json"
    )
    errors.extend(adjudication_errors)
    return {
        "schema": "temporary-probe-obligation-screen-validation/v1",
        "valid": not errors,
        "errors": errors,
        "expected_runs": 2,
        "observed_run_metadata": sum(
            1 for path in campaign_root.glob("*/run-metadata.json") if path.is_file()
        ),
        "endpoint_observations": endpoint_observations,
        "grader_outcomes_valid": not _validate_grader_results(
            campaign_root / "external-grader-results.json", manifest["grader_sha256"]
        ),
        "recall_adjudicated": adjudication is not None and not adjudication_errors,
        "independent_verification": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--manifest", type=Path, required=True)
    preflight.add_argument("--source-root", type=Path, required=True)
    preflight.add_argument("--archive", type=Path, required=True)
    preflight.add_argument("--target-root", type=Path, required=True)
    preflight.add_argument("--venv", type=Path, required=True)
    preflight.add_argument("--rg", type=Path, required=True)
    final = subparsers.add_parser("final")
    final.add_argument("--campaign-root", type=Path, required=True)
    final.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")
    if args.command == "preflight":
        result = validate_preflight(
            manifest_path=args.manifest,
            source_root=args.source_root,
            archive_path=args.archive,
            target_root=args.target_root,
            venv=args.venv,
            rg_path=args.rg,
        )
    else:
        result = validate_campaign(
            campaign_root=args.campaign_root,
            source_root=args.source_root,
        )
    _write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
