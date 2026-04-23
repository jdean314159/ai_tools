from __future__ import annotations

from datetime import datetime, timezone

from llm_inspector_ui.state.models import RunArtifact, WorkbenchProfile
from llm_inspector_ui.state.session_store import SessionStore


def test_session_store_round_trip(tmp_path):
    store = SessionStore(tmp_path / "workbench.sqlite")

    session = store.create_session("Test Session")
    assert session.title == "Test Session"

    user_turn = store.add_turn(session.session_id, "user", "hello")
    assistant_turn = store.add_turn(session.session_id, "assistant", "world")

    turns = store.list_turns(session.session_id)
    assert [t.role for t in turns] == ["user", "assistant"]
    assert [t.text for t in turns] == ["hello", "world"]

    run = RunArtifact(
        run_id="run-1",
        session_id=session.session_id,
        turn_id=user_turn.turn_id,
        assistant_turn_id=assistant_turn.turn_id,
        created_at=datetime.now(timezone.utc),
        engine_id="echo",
        model_id="echo",
        augmenter_id="baseline",
        mode="chat",
        status="ok",
        user_text="hello",
        prompt="## User\nhello",
        response_text="world",
        trace={"final_prompt": "## User\nhello"},
        engine_metrics={"latency_ms": 1},
        settings={"temperature": 0.0},
        error=None,
    )
    store.save_run(run)

    runs = store.list_runs(session.session_id)
    assert len(runs) == 1
    assert runs[0].run_id == "run-1"
    assert runs[0].status == "ok"
    assert runs[0].trace["final_prompt"] == "## User\nhello"

    profile = WorkbenchProfile(
        profile_id="profile-1",
        name="Baseline Echo",
        engine_id="echo",
        model_id="echo",
        augmenter_ids=["baseline"],
    )
    store.save_profile(profile)

    loaded_profile = store.get_profile("profile-1")
    assert loaded_profile is not None
    assert loaded_profile.name == "Baseline Echo"

    profiles = store.list_profiles()
    assert len(profiles) == 1
    assert profiles[0].profile_id == "profile-1"

    store.delete_profile("profile-1")
    assert store.get_profile("profile-1") is None