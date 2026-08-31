from __future__ import annotations

from datetime import datetime, timedelta, timezone

from llm_inspector_ui.panels.compare_panel import _group_runs_by_turn
from llm_inspector_ui.state.models import RunArtifact


def _run(
    *, run_id: str, turn_id: str, augmenter_id: str, created_at: datetime, mode: str = "compare"
) -> RunArtifact:
    return RunArtifact(
        run_id=run_id,
        session_id="session-1",
        turn_id=turn_id,
        assistant_turn_id=None,
        created_at=created_at,
        engine_id="echo",
        model_id="echo",
        augmenter_id=augmenter_id,
        mode=mode,
        user_text="hello",
        prompt="prompt",
        response_text="response",
        trace={"token_accounting": {}},
    )


def test_group_runs_by_turn_orders_newest_group_first():
    base = datetime.now(timezone.utc)

    runs = [
        _run(run_id="r1", turn_id="t1", augmenter_id="baseline", created_at=base),
        _run(
            run_id="r2", turn_id="t1", augmenter_id="engram", created_at=base + timedelta(seconds=1)
        ),
        _run(
            run_id="r3",
            turn_id="t2",
            augmenter_id="baseline",
            created_at=base + timedelta(seconds=10),
        ),
        _run(
            run_id="r4",
            turn_id="t2",
            augmenter_id="engram",
            created_at=base + timedelta(seconds=11),
        ),
    ]

    grouped = _group_runs_by_turn(runs)

    assert [turn_id for turn_id, _group in grouped] == ["t2", "t1"]
    assert [r.run_id for r in grouped[0][1]] == ["r3", "r4"]
    assert [r.run_id for r in grouped[1][1]] == ["r1", "r2"]
