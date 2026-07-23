"""Build the frozen NAV-VERIFIABLE-00 candidate pool and selection manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from agent_lib.eval.verifiable_campaign import build_campaign_admission_manifest
from agent_lib.eval.verifiable_navigation import (
    PythonRelationOracle,
    VerifiableTask,
    build_task_admission_manifest,
)
from agent_lib.eval.verifiable_selection import (
    build_candidate_pool,
    select_campaign_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pool = build_candidate_pool(args.snapshot)
    selection = select_campaign_candidates(pool)
    snapshot_roots = {
        _snapshot_id(Path(raw_root)): Path(raw_root).resolve(strict=True)
        for raw_root in args.snapshot
    }
    admissions = []
    task_sets = []
    for snapshot_id in sorted(
        {str(item["snapshot_id"]) for item in selection["selected"]}
    ):
        root = snapshot_roots[snapshot_id]
        selected = [
            item
            for item in selection["selected"]
            if item["snapshot_id"] == snapshot_id
        ]
        tasks = [_task_from_candidate(item) for item in selected]
        oracle = PythonRelationOracle(root)
        admission = build_task_admission_manifest(tasks, oracle=oracle)
        admissions.append(admission)
        task_set = {
            "schema_version": 1,
            "track": "NAV-VERIFIABLE-00",
            "sources": admission["source_hashes"],
            "tasks": [_task_payload(task) for task in tasks],
        }
        short_id = snapshot_id[:12]
        task_set_name = f"task-set-{short_id}.json"
        admission_name = f"admission-{short_id}.json"
        (output_dir / task_set_name).write_text(
            json.dumps(task_set, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / admission_name).write_text(
            json.dumps(admission, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        task_sets.append(
            {
                "snapshot_id": snapshot_id,
                "source_root": _portable_path(root),
                "task_set": task_set_name,
                "admission": admission_name,
            }
        )
    campaign_admission = build_campaign_admission_manifest(admissions)
    (output_dir / "campaign-admission.json").write_text(
        json.dumps(campaign_admission, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "run-plan.json").write_text(
        json.dumps(
            {
                "track": "NAV-VERIFIABLE-00",
                "candidate_pool_sha256": pool["candidate_pool_sha256"],
                "candidate_selection_sha256": selection[
                    "candidate_selection_sha256"
                ],
                "campaign_manifest_sha256": campaign_admission[
                    "campaign_manifest_sha256"
                ],
                "task_sets": task_sets,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "candidate-pool.json").write_text(
        json.dumps(pool, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "candidate-selection.json").write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tier_counts: dict[str, int] = {}
    for item in selection["selected"]:
        tier = item["difficulty"]["tier"]
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    print(
        json.dumps(
            {
                "candidate_pool_sha256": pool["candidate_pool_sha256"],
                "candidate_selection_sha256": selection[
                    "candidate_selection_sha256"
                ],
                "campaign_manifest_sha256": campaign_admission[
                    "campaign_manifest_sha256"
                ],
                "pool_size": len(pool["candidates"]),
                "selected_tiers": tier_counts,
            },
            sort_keys=True,
        )
    )
    return 0


def _snapshot_id(root: Path) -> str:
    source_hashes = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    canonical = json.dumps(
        source_hashes, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _portable_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _task_from_candidate(candidate: dict) -> VerifiableTask:
    return VerifiableTask(
        task_id=str(candidate["task_id"]),
        kind=str(candidate["kind"]),  # type: ignore[arg-type]
        question=str(candidate["question"]),
        path=str(candidate["path"]),
        symbol=str(candidate["symbol"]),
        endpoint=str(candidate.get("endpoint") or ""),
        line=(
            int(candidate["line"])
            if isinstance(candidate.get("line"), int)
            else None
        ),
        goal_requirements=tuple(
            (str(item["goal_id"]), str(item["requirement"]))
            for item in candidate["goal_requirements"]
        ),
    )


def _task_payload(task: VerifiableTask) -> dict:
    payload = {
        "task_id": task.task_id,
        "kind": task.kind,
        "question": task.question,
        "path": task.path,
        "symbol": task.symbol,
        "goal_requirements": [
            {"goal_id": goal_id, "requirement": requirement}
            for goal_id, requirement in task.goal_requirements
        ],
    }
    if task.endpoint:
        payload["endpoint"] = task.endpoint
    if task.line is not None:
        payload["line"] = task.line
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
