from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm_inspector_ui.services.submission import compute_submission_readiness
from llm_inspector_ui.app import compute_submission_readiness as app_submission_readiness


class AugmenterReadinessService:
    def __init__(self, readiness_by_id):
        self.readiness_by_id = readiness_by_id

    def get_augmenter_readiness(self, augmenter_id, *, options):
        return self.readiness_by_id[augmenter_id]


def readiness(identifier: str, *, can_run: bool, severity: str = "ok"):
    return SimpleNamespace(
        augmenter_id=identifier,
        can_run=can_run,
        severity=severity,
        message=f"{identifier}: {severity}",
        details={},
    )


@pytest.mark.parametrize(
    ("engine_ready", "branches", "can_submit", "severity"),
    [
        (False, {"baseline": readiness("baseline", can_run=True)}, False, "error"),
        (True, {"rag": readiness("rag", can_run=False, severity="error")}, False, "error"),
        (
            True,
            {
                "baseline": readiness("baseline", can_run=True),
                "rag": readiness("rag", can_run=False, severity="warning"),
            },
            True,
            "warning",
        ),
        (True, {"baseline": readiness("baseline", can_run=True)}, True, "ok"),
    ],
)
def test_compute_submission_readiness(
    engine_ready: bool,
    branches: dict[str, SimpleNamespace],
    can_submit: bool,
    severity: str,
) -> None:
    engine_readiness = SimpleNamespace(
        can_run=engine_ready,
        severity="ok" if engine_ready else "error",
        message="engine ready" if engine_ready else "engine unavailable",
    )
    controls = {
        "run_readiness": engine_readiness,
        "augmenter_ids": list(branches),
        "augmenter_options": {},
    }

    result = compute_submission_readiness(
        controls,
        augmenter_service=AugmenterReadinessService(branches),
    )

    assert result["can_submit"] is can_submit
    assert result["severity"] == severity
    assert result["engine_readiness"] is engine_readiness
    assert result["branch_readiness"] == list(branches.values())


def test_app_submission_readiness_export_preserves_identity() -> None:
    assert app_submission_readiness is compute_submission_readiness
