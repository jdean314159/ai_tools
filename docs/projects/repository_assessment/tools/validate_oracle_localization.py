"""Validate frozen inputs and completed evidence for the Ornith localization test."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from typing import Any


MODEL = "Ornith-1.5-35B-Q4_K_M.gguf"
SEEDS = {17, 31, 47}
EXPECTED_GRADERS = (
    (
        "23c1549d5aae3ac67454aade1b725f2931770014",
        "49026eac3d2e24b02641bf9db0a76e94909e9386",
        "test_cross_package_defects_at_23c1549_corrected.py",
        2,
    ),
    (
        "7d37920a81a9cb672c24af3a55557621e5c5009f",
        "8e2e9e5f2c45c935bdc3afa2479a08dc702b44db",
        "test_engram_boundary_defects_at_7d37920.py",
        3,
    ),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git_span(repo_root: Path, item: dict[str, Any]) -> str:
    data = subprocess.check_output(
        ["git", "show", f"{item['commit']}:{item['path']}"], cwd=repo_root, text=True
    ).splitlines()
    return "\n".join(data[item["start_line"] - 1 : item["end_line"]]) + "\n"


def validate_inputs(campaign_root: Path, repo_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    spans = load_json(campaign_root / "span-manifest.json")
    oracle_payload = load_json(campaign_root / "oracle-manifest.json")
    matrix = load_json(campaign_root / "run-matrix.json")
    prompts = load_json(campaign_root / "prompts.json")
    controls = load_json(campaign_root / "scorer-controls.json")
    items = spans.get("items", [])
    oracles = oracle_payload.get("oracles", [])
    if spans.get("schema") != "oracle-localization-span-manifest/v2":
        errors.append("span manifest schema")
    if len(items) != 10:
        errors.append("span manifest must contain ten items")
    item_ids = {row.get("item_id") for row in items}
    if len(item_ids) != 10:
        errors.append("span item IDs are not unique")
    for item in items:
        try:
            text = git_span(repo_root, item)
        except Exception as exc:
            errors.append(f"{item.get('item_id')}: source unavailable: {exc}")
            continue
        if text != item.get("text"):
            errors.append(f"{item['item_id']}: text mismatch")
        if sha256_bytes(text.encode()) != item.get("sha256"):
            errors.append(f"{item['item_id']}: digest mismatch")
        if item.get("line_count") != item.get("end_line") - item.get("start_line") + 1:
            errors.append(f"{item['item_id']}: line count mismatch")
    by_pair: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_pair.setdefault(item.get("pair_id"), []).append(item)
    if set(by_pair) != {row.get("pair_id") for row in oracles}:
        errors.append("span/oracle pair mismatch")
    for pair_id, rows in by_pair.items():
        if {row.get("kind") for row in rows} != {"defect", "negative"}:
            errors.append(f"{pair_id}: pair roles")
            continue
        defect = next(row for row in rows if row["kind"] == "defect")
        negative = next(row for row in rows if row["kind"] == "negative")
        ratio = max(defect["line_count"], negative["line_count"]) / min(
            defect["line_count"], negative["line_count"]
        )
        if defect["path"] != negative["path"] or ratio > 2:
            errors.append(f"{pair_id}: negative is not structurally matched")
        if defect["text"] == negative["text"]:
            errors.append(f"{pair_id}: defect and negative text identical")
    for oracle in oracles:
        if len(oracle.get("match_groups", [])) != 3:
            errors.append(f"{oracle.get('pair_id')}: matcher group count")
        for group in oracle.get("match_groups", []):
            for pattern in group:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"{oracle.get('pair_id')}: bad regex {pattern}: {exc}")
    runs = matrix.get("runs", [])
    if len(runs) != 60 or [row.get("order") for row in runs] != list(range(1, 61)):
        errors.append("run matrix size/order")
    for condition in ("B", "C"):
        selected = [row for row in runs if row.get("condition") == condition]
        if len(selected) != 30:
            errors.append(f"condition {condition}: count")
        for item_id in item_ids:
            seeds = {row.get("seed") for row in selected if row.get("item_id") == item_id}
            if seeds != SEEDS:
                errors.append(f"condition {condition} item {item_id}: seeds")
    if matrix.get("model") != MODEL or matrix.get("temperature") != 0:
        errors.append("model settings")
    if matrix.get("thinking") is not False or matrix.get("max_tokens") != 512:
        errors.append("generation settings")
    if "{hypothesis}" in prompts.get("condition_b_user_template", ""):
        errors.append("condition B leaks hypothesis")
    if "{hypothesis}" not in prompts.get("condition_c_user_template", ""):
        errors.append("condition C omits hypothesis")
    if not controls.get("all_passed") or len(controls.get("controls", [])) < 4:
        errors.append("scorer controls")
    return {
        "valid": not errors,
        "errors": errors,
        "span_items": len(items),
        "oracle_pairs": len(oracles),
        "planned_runs": len(runs),
        "scorer_controls_passed": controls.get("all_passed") is True,
    }


def _extract_commit(repo_root: Path, commit: str, output: Path) -> None:
    archive = subprocess.check_output(["git", "archive", "--format=tar", commit], cwd=repo_root)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        bundle.extractall(output, filter="data")


def _pytest_counts(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0}
    for key in counts:
        matches = re.findall(rf"(\d+) {key}", output)
        if matches:
            counts[key] = int(matches[-1])
    return counts


def run_graders(repo_root: Path, tools_dir: Path, python: Path) -> list[dict[str, Any]]:
    results = []
    with tempfile.TemporaryDirectory(prefix="oracle-localization-graders-") as temp_value:
        temp = Path(temp_value)
        for target, reference, grader_name, expected in EXPECTED_GRADERS:
            row: dict[str, Any] = {
                "target": target,
                "corrected_reference": reference,
                "grader": grader_name,
                "expected_tests": expected,
                "runs": [],
            }
            for role, commit in (("target", target), ("corrected_reference", reference)):
                export = temp / f"{commit}-{role}"
                export.mkdir()
                _extract_commit(repo_root, commit, export)
                source_paths = [str(path) for path in sorted(export.glob("*/src"))]
                env = {
                    **os.environ,
                    "ASSESSMENT_REPO_ROOT": str(export),
                    "PYTHONPATH": os.pathsep.join(source_paths),
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
                completed = subprocess.run(
                    [
                        str(python),
                        "-m",
                        "pytest",
                        "-c",
                        "/dev/null",
                        "--noconftest",
                        "-p",
                        "no:cacheprovider",
                        "-q",
                        str(tools_dir / grader_name),
                    ],
                    cwd=export,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                output = completed.stdout + completed.stderr
                counts = _pytest_counts(output)
                expected_ok = (
                    counts["failed"] == expected and completed.returncode == 1
                    if role == "target"
                    else counts["passed"] == expected and completed.returncode == 0
                )
                row["runs"].append(
                    {
                        "role": role,
                        "commit": commit,
                        "returncode": completed.returncode,
                        **counts,
                        "output_sha256": sha256_bytes(output.encode()),
                        "expected_outcome": expected_ok,
                    }
                )
            row["valid"] = all(run["expected_outcome"] for run in row["runs"])
            results.append(row)
    return results


def compare_endpoint(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    left = before.get("fingerprint", {})
    right = after.get("fingerprint", {})
    for key in set(left) | set(right):
        if key == "slots":
            continue
        if left.get(key) != right.get(key):
            errors.append(f"endpoint changed:{key}")
    left_slots = left.get("slots", [])
    right_slots = right.get("slots", [])
    if len(left_slots) != len(right_slots):
        errors.append("endpoint slot count changed")
    else:
        for index, (old, new) in enumerate(zip(left_slots, right_slots)):
            for key in ("id", "n_ctx", "speculative"):
                if old.get(key) != new.get(key):
                    errors.append(f"endpoint slot {index} changed:{key}")
            old_type = old.get("speculative_types")
            new_type = new.get("speculative_types")
            if old_type is not None and new_type is not None and old_type != new_type:
                errors.append(f"endpoint slot {index} changed:speculative_types")
    if before.get("health") != "ok" or after.get("health") != "ok":
        errors.append("endpoint health")
    return errors


def validate_generation_set(campaign_root: Path, generation_set: str) -> dict[str, Any]:
    errors: list[str] = []
    matrix = load_json(campaign_root / "run-matrix.json")
    spans = load_json(campaign_root / "span-manifest.json")
    items = {row["item_id"]: row for row in spans["items"]}
    root = campaign_root / generation_set
    before_path = root / "endpoint-before.json"
    after_path = root / "endpoint-after.json"
    if not before_path.is_file() or not after_path.is_file():
        errors.append("missing endpoint snapshots")
    else:
        errors.extend(compare_endpoint(load_json(before_path), load_json(after_path)))
    observed = 0
    for run in matrix["runs"]:
        run_root = root / run["run_id"]
        paths = {
            "metadata": run_root / "run-metadata.json",
            "transcript": run_root / "transcript.jsonl",
            "raw": run_root / "raw-response.txt",
            "parsed": run_root / "parsed-response.json",
        }
        if not all(path.is_file() for path in paths.values()):
            errors.append(f"{run['run_id']}: missing artifacts")
            continue
        observed += 1
        meta = load_json(paths["metadata"])
        for key in ("run_id", "condition", "item_id", "pair_id", "truth", "seed"):
            if meta.get(key) != run.get(key):
                errors.append(f"{run['run_id']}: metadata {key}")
        if meta.get("validity") != "valid" or meta.get("lifecycle") != "final":
            errors.append(f"{run['run_id']}: invalid lifecycle")
        if meta.get("model") != MODEL or meta.get("seed_status") != "accepted":
            errors.append(f"{run['run_id']}: model/seed")
        raw = paths["raw"].read_bytes()
        transcript = [json.loads(line) for line in paths["transcript"].read_text().splitlines()]
        if len(transcript) != 2 or [row.get("event") for row in transcript] != ["request", "response"]:
            errors.append(f"{run['run_id']}: transcript shape")
            continue
        response = transcript[1]
        if response.get("content", "").encode() != raw:
            errors.append(f"{run['run_id']}: raw response mismatch")
        if meta.get("raw_response_sha256") != sha256_bytes(raw):
            errors.append(f"{run['run_id']}: raw digest")
        if meta.get("transcript_sha256") != sha256_bytes(paths["transcript"].read_bytes()):
            errors.append(f"{run['run_id']}: transcript digest")
        if meta.get("usage") != response.get("usage"):
            errors.append(f"{run['run_id']}: usage mismatch")
        if meta.get("elapsed_ms") != response.get("elapsed_ms"):
            errors.append(f"{run['run_id']}: elapsed mismatch")
        if meta.get("span_sha256") != items[run["item_id"]]["sha256"]:
            errors.append(f"{run['run_id']}: span digest")
    return {
        "valid": not errors,
        "errors": errors,
        "expected_runs": 60,
        "observed_valid_runs": observed,
        "generation_set": generation_set,
        "token_and_elapsed_fields_checked": observed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--run-graders", action="store_true")
    parser.add_argument("--generation-set")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.campaign_root = args.campaign_root.resolve()
    args.repo_root = args.repo_root.resolve()
    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")
    result: dict[str, Any] = {
        "schema": "oracle-localization-validation/v1",
        "inputs": validate_inputs(args.campaign_root, args.repo_root),
    }
    if args.run_graders:
        grader_rows = run_graders(
            args.repo_root,
            args.repo_root / "docs/projects/repository_assessment/tools",
            args.repo_root / ".venv/bin/python",
        )
        result["graders"] = grader_rows
        result["graders_valid"] = all(row["valid"] for row in grader_rows)
    if args.generation_set:
        result["generation_set"] = validate_generation_set(
            args.campaign_root, args.generation_set
        )
    result["valid"] = (
        result["inputs"]["valid"]
        and result.get("graders_valid", True)
        and result.get("generation_set", {}).get("valid", True)
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
