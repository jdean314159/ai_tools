from __future__ import annotations


def compute_submission_readiness(
    controls: dict[str, object], augmenter_service
) -> dict[str, object]:
    engine_readiness = controls["run_readiness"]
    augmenter_ids = list(controls["augmenter_ids"])
    augmenter_options = dict(controls.get("augmenter_options", {}))

    branch_readiness = [
        augmenter_service.get_augmenter_readiness(
            augmenter_id,
            options=augmenter_options.get(augmenter_id, {}),
        )
        for augmenter_id in augmenter_ids
    ]

    if not engine_readiness.can_run:
        return {
            "can_submit": False,
            "severity": engine_readiness.severity,
            "message": engine_readiness.message,
            "engine_readiness": engine_readiness,
            "branch_readiness": branch_readiness,
        }

    runnable_branches = [r for r in branch_readiness if r.can_run]
    if not runnable_branches:
        return {
            "can_submit": False,
            "severity": "error",
            "message": "No selected augmenter branches are runnable.",
            "engine_readiness": engine_readiness,
            "branch_readiness": branch_readiness,
        }

    skipped = [r for r in branch_readiness if not r.can_run]
    if skipped:
        return {
            "can_submit": True,
            "severity": "warning",
            "message": f"{len(skipped)} branch(es) will be skipped; {len(runnable_branches)} branch(es) will run.",
            "engine_readiness": engine_readiness,
            "branch_readiness": branch_readiness,
        }

    return {
        "can_submit": True,
        "severity": "ok",
        "message": "All selected branches are runnable.",
        "engine_readiness": engine_readiness,
        "branch_readiness": branch_readiness,
    }
