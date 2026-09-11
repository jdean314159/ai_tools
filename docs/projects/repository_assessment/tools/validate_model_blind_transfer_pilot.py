"""Validate the frozen four-run Ornith model-blind transfer pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


STAGED_RUNNER_SHA256 = "4f275d6c44b5057a34076866328d362c35bcd9f86feb9435174ce0c634325c98"
ADAPTIVE_RUNNER_SHA256 = "a319a1853ef1605e9b0f59a7cb84553315c7a1716fb00e922d66a4df7e1aabd8"
MODEL_LABEL = "Ornith-1.5-35B-Q4_K_M.gguf"

TARGETS = {
    "target-23c1549": {
        "target_commit": "23c1549d5aae3ac67454aade1b725f2931770014",
        "target_tree": "d4faa7c547ab8e34f251124c7e5ca7a9dcbf6364",
        "target_archive_sha256": (
            "ba24146927228771ccefc078cf8732e0a1abb77e3d4a77ff699205742413d1b0"
        ),
        "corrected_reference": "49026eac3d2e24b02641bf9db0a76e94909e9386",
        "grader": "test_cross_package_defects_at_23c1549.py",
        "grader_sha256": "6e2a8a48b3baf28ae0c5eb6c52784cba16c12d23c9ac37814666f23bc69524ab",
        "corrected_grader": "test_cross_package_defects_at_23c1549_corrected.py",
        "corrected_grader_sha256": (
            "d1a589561ef0d724ec13e9c502d2130ebf6014ae1778db673296c866f2e6c23a"
        ),
        "valid_defect_count": 2,
        "runs": (
            ("01-v1-seed17", "staged_scout_verifier_critic_synthesis", 17, "staged"),
            ("02-v2-2-seed17", "adaptive_staged_v2_2", 17, "adaptive"),
        ),
    },
    "target-7d37920": {
        "target_commit": "7d37920a81a9cb672c24af3a55557621e5c5009f",
        "target_tree": "0177f7c8288a42ca771084c42362ddb6f90a9640",
        "target_archive_sha256": (
            "02e68e5c7cb349f1c6e3011fd6f0265ebdf6a87fa753bef932fabfd271bd8769"
        ),
        "corrected_reference": "8e2e9e5f2c45c935bdc3afa2479a08dc702b44db",
        "grader": "test_engram_boundary_defects_at_7d37920.py",
        "grader_sha256": "6df8cf5c9ad7eb29f06e9e0db34dedd4801bdfaa66860028b53f98ddb484efe8",
        "valid_defect_count": 3,
        "runs": (
            ("01-v2-2-seed31", "adaptive_staged_v2_2", 31, "adaptive"),
            ("02-v1-seed31", "staged_scout_verifier_critic_synthesis", 31, "staged"),
        ),
    },
}

PROMPT_SHA256 = {
    "staged": {
        "scout": "cf172ae87df99a5a4627ff9755ae909ee3f4dd8260d5aeb152c9d43eb9769515",
        "synthesis": "fe48bcdddf0d091344219e8f2a57e060a0e1e6bfa092cd88483240195b324779",
        "verifier": "4adeb0217c704665741090b130c4e7deec461340a7ae51bc6b62c4c1108352a6",
    },
    "adaptive": {
        "scout": "4cd05834f9f64e4bc8dbabd493200811a6ab2d1d12e50239ea676528603f2a42",
        "selection": "35a7a1704797c8dbd1aa265198f323e8fa5f3e03ac70761d218f4136e8e24286",
        "verifier": "1ff7f5200f3dee9c834415418d33f733f9d5bd607e9d74511ab344a72b9f5ca0",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def compare_endpoint_snapshots(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Compare material endpoint state while preserving nullable slot telemetry."""
    errors: list[str] = []
    observations: list[str] = []
    before_fingerprint = before.get("fingerprint", {})
    after_fingerprint = after.get("fingerprint", {})
    if not isinstance(before_fingerprint, dict) or not isinstance(after_fingerprint, dict):
        return ["endpoint fingerprint body is not an object"], observations

    before_stable = {key: value for key, value in before_fingerprint.items() if key != "slots"}
    after_stable = {key: value for key, value in after_fingerprint.items() if key != "slots"}
    if before_stable != after_stable:
        errors.append("endpoint stable configuration changed")

    before_slots = before_fingerprint.get("slots", [])
    after_slots = after_fingerprint.get("slots", [])
    if not isinstance(before_slots, list) or not isinstance(after_slots, list):
        errors.append("endpoint slots are not arrays")
        return errors, observations
    if len(before_slots) != len(after_slots):
        errors.append("endpoint slot count changed")
        return errors, observations

    for index, (before_slot, after_slot) in enumerate(zip(before_slots, after_slots)):
        if not isinstance(before_slot, dict) or not isinstance(after_slot, dict):
            errors.append(f"endpoint slot {index} is not an object")
            continue
        for field in ("id", "is_processing", "n_ctx", "speculative"):
            if before_slot.get(field) != after_slot.get(field):
                errors.append(f"endpoint slot {index} {field} changed")
        before_type = before_slot.get("speculative_types")
        after_type = after_slot.get("speculative_types")
        if before_type is not None and after_type is not None and before_type != after_type:
            errors.append(f"endpoint slot {index} speculative_types changed")
        elif before_type != after_type:
            observations.append(
                f"endpoint slot {index} speculative_types telemetry changed "
                f"from {before_type!r} to {after_type!r}"
            )
    return errors, observations


def validate_run(
    run_dir: Path,
    *,
    target: dict[str, Any],
    condition: str,
    seed: int,
    runner_kind: str,
) -> list[str]:
    errors: list[str] = []
    metadata_path = run_dir / "run-metadata.json"
    if not metadata_path.is_file():
        return [f"missing run metadata: {metadata_path}"]
    metadata = _read_json(metadata_path)
    for field in ("target_commit", "target_tree", "target_archive_sha256"):
        if metadata.get(field) != target[field]:
            errors.append(f"{run_dir.name}: {field} mismatch")
    if metadata.get("condition") != condition:
        errors.append(f"{run_dir.name}: condition mismatch")
    if metadata.get("seed") != seed:
        errors.append(f"{run_dir.name}: seed mismatch")
    if metadata.get("model") != MODEL_LABEL:
        errors.append(f"{run_dir.name}: model mismatch")
    if metadata.get("validity") == "invalid":
        errors.append(f"{run_dir.name}: marked infrastructure-invalid")
    if metadata.get("prompt_sha256") != PROMPT_SHA256[runner_kind]:
        errors.append(f"{run_dir.name}: prompt digest mismatch")
    if metadata.get("shell_tool_calls", 46) > 45:
        errors.append(f"{run_dir.name}: shell-call ceiling exceeded")

    transcript = run_dir / "transcript.jsonl"
    report_name = "raw-model-report.md" if runner_kind == "staged" else "raw-controller-report.md"
    report = run_dir / report_name
    for path, field in ((transcript, "transcript_sha256"), (report, "report_sha256")):
        if not path.is_file():
            errors.append(f"{run_dir.name}: missing {path.name}")
        elif metadata.get(field) != _sha256(path):
            errors.append(f"{run_dir.name}: {field} mismatch")

    if runner_kind == "adaptive":
        dossier_hashes = metadata.get("dossiers", {}).get("sha256", {})
        for scope, expected in dossier_hashes.items():
            dossier = run_dir / "dossiers" / f"{scope}.json"
            if not dossier.is_file() or _sha256(dossier) != expected:
                errors.append(f"{run_dir.name}: dossier mismatch for {scope}")
    return errors


def validate_campaign(campaign_root: Path, source_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    endpoint_observations: dict[str, list[str]] = {}
    runner_paths = {
        "staged": source_root / "tools" / "run_staged_assessment.py",
        "adaptive": source_root / "tools" / "run_adaptive_staged_assessment.py",
    }
    expected_runner_hashes = {
        "staged": STAGED_RUNNER_SHA256,
        "adaptive": ADAPTIVE_RUNNER_SHA256,
    }
    for kind, path in runner_paths.items():
        if not path.is_file() or _sha256(path) != expected_runner_hashes[kind]:
            errors.append(f"{kind} runner digest mismatch")

    grader_results_path = campaign_root / "independent-grader-results.json"
    grader_outcomes_valid = True
    if not grader_results_path.is_file():
        errors.append("missing independent grader results")
        grader_outcomes_valid = False
        grader_results: dict[str, Any] = {}
    else:
        grader_results = _read_json(grader_results_path)
    recorded_targets = grader_results.get("targets", {})
    if not isinstance(recorded_targets, dict):
        errors.append("grader targets are not an object")
        grader_outcomes_valid = False
        recorded_targets = {}
    frozen_grader_semantic_invalidations = 0
    for target_name, target in TARGETS.items():
        grader_path = source_root / "tools" / target["grader"]
        if not grader_path.is_file() or _sha256(grader_path) != target["grader_sha256"]:
            errors.append(f"{target_name}: grader digest mismatch")
            grader_outcomes_valid = False
        recorded = recorded_targets.get(target_name, {})
        expected_fields: dict[str, Any] = {
            "commit": target["target_commit"],
            "corrected_reference": target["corrected_reference"],
            "valid_defect_count": target["valid_defect_count"],
        }
        if target_name == "target-23c1549":
            corrected_grader_path = source_root / "tools" / target["corrected_grader"]
            if (
                not corrected_grader_path.is_file()
                or _sha256(corrected_grader_path) != target["corrected_grader_sha256"]
            ):
                errors.append(f"{target_name}: corrected grader digest mismatch")
                grader_outcomes_valid = False
            expected_fields.update(
                {
                    "frozen_grader": {
                        "path": (
                            "docs/projects/repository_assessment/tools/"
                            "test_cross_package_defects_at_23c1549.py"
                        ),
                        "sha256": target["grader_sha256"],
                        "target_result": {"failed": 3, "passed": 0, "returncode": 1},
                        "corrected_reference_result": {
                            "failed": 0,
                            "passed": 3,
                            "returncode": 0,
                        },
                    },
                    "corrected_grader": {
                        "path": (
                            "docs/projects/repository_assessment/tools/"
                            "test_cross_package_defects_at_23c1549_corrected.py"
                        ),
                        "sha256": target["corrected_grader_sha256"],
                        "target_result": {"failed": 2, "passed": 0, "returncode": 1},
                        "corrected_reference_result": {
                            "failed": 0,
                            "passed": 2,
                            "returncode": 0,
                        },
                    },
                }
            )
            semantic_invalidation = (
                recorded.get("semantic_invalidation", {}) if isinstance(recorded, dict) else {}
            )
            if semantic_invalidation.get("invalid_test") != (
                "test_shipped_engine_config_contains_no_private_deployment_address"
            ):
                errors.append(f"{target_name}: missing frozen-grader semantic invalidation")
                grader_outcomes_valid = False
            else:
                frozen_grader_semantic_invalidations += 1
        else:
            expected_fields.update(
                {
                    "grader": {
                        "path": (
                            "docs/projects/repository_assessment/tools/"
                            "test_engram_boundary_defects_at_7d37920.py"
                        ),
                        "sha256": target["grader_sha256"],
                    },
                    "target_result": {"failed": 3, "passed": 0, "returncode": 1},
                    "corrected_reference_result": {
                        "failed": 0,
                        "passed": 3,
                        "returncode": 0,
                    },
                }
            )
        for field, expected in expected_fields.items():
            if not isinstance(recorded, dict) or recorded.get(field) != expected:
                errors.append(f"{target_name}: grader {field} mismatch")
                grader_outcomes_valid = False

    run_count = 0
    for target_name, target in TARGETS.items():
        target_root = campaign_root / target_name
        before = target_root / "endpoint-before.json"
        after = target_root / "endpoint-after.json"
        if not before.is_file() or not after.is_file():
            errors.append(f"{target_name}: missing endpoint pair")
        else:
            before_snapshot = _read_json(before)
            after_snapshot = _read_json(after)
            endpoint_errors, observations = compare_endpoint_snapshots(
                before_snapshot, after_snapshot
            )
            errors.extend(f"{target_name}: {error}" for error in endpoint_errors)
            endpoint_observations[target_name] = observations
            if before_snapshot.get("health") != "ok" or after_snapshot.get("health") != "ok":
                errors.append(f"{target_name}: endpoint health was not ok")

        for run_name, condition, seed, runner_kind in target["runs"]:
            run_count += 1
            errors.extend(
                validate_run(
                    target_root / run_name,
                    target=target,
                    condition=condition,
                    seed=seed,
                    runner_kind=runner_kind,
                )
            )

    return {
        "schema": "temporary-ornith-model-blind-transfer-validation/v1",
        "valid": not errors,
        "expected_runs": 4,
        "observed_run_metadata": sum(
            1 for path in campaign_root.glob("target-*/*/run-metadata.json") if path.is_file()
        ),
        "validated_runs": run_count,
        "errors": errors,
        "endpoint_observations": endpoint_observations,
        "grader_outcomes_valid": grader_outcomes_valid,
        "frozen_grader_semantic_invalidations": frozen_grader_semantic_invalidations,
        "recall_adjudicated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository-assessment directory containing the tools subdirectory.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_campaign(args.campaign_root, args.source_root)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error(f"refusing to overwrite {args.output}")
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
