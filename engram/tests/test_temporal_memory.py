from __future__ import annotations

from engram import ProjectMemory, Telemetry


def test_temporal_updates_hide_superseded_current_but_retain_history(tmp_path):
    memory = ProjectMemory(base_dir=tmp_path, project_id="temporal", session_id="s1")
    first = memory.store_temporal_episode(
        "Atlas region was us-east-1.", topic_key="atlas::region", action="set",
        importance=1.0, bypass_filter=True,
    )
    second = memory.store_temporal_episode(
        "Atlas region is now eu-central-1.", topic_key="atlas::region", action="update",
        importance=1.0, bypass_filter=True,
    )

    current = memory.search_episodes("Atlas region", n=5)
    historical = memory.search_episodes("Atlas region", n=5, include_historical=True)

    assert [item.episode_id for item in current] == [second]
    assert {item.episode_id for item in historical} == {first, second}
    old = next(item for item in historical if item.episode_id == first)
    assert old.metadata["temporal_status"] == "superseded"
    assert old.metadata["superseded_by"] == second
    assert next(item for item in current if item.episode_id == second).metadata["supersedes"] == [first]


def test_retraction_is_current_evidence_and_suppresses_prior_value(tmp_path):
    memory = ProjectMemory(base_dir=tmp_path, project_id="retract", session_id="s1")
    old = memory.store_temporal_episode(
        "Beacon retention is 45 days.", topic_key="beacon::retention", action="set",
        importance=1.0, bypass_filter=True,
    )
    retraction = memory.store_temporal_episode(
        "Beacon has no current retention period.", topic_key="beacon::retention", action="retract",
        importance=1.0, bypass_filter=True,
    )

    current = memory.search_episodes("Beacon current retention", n=5)
    historical = memory.search_episodes("Beacon retention", n=5, include_historical=True)

    assert [item.episode_id for item in current] == [retraction]
    assert {item.episode_id for item in historical} == {old, retraction}
    assert current[0].metadata["temporal_action"] == "retract"


def test_prompt_surfaces_temporal_and_budget_diagnostics_with_provenance(tmp_path):
    events = []
    telemetry = Telemetry()
    telemetry.add_sink(events.append)
    memory = ProjectMemory(
        base_dir=tmp_path, project_id="trace", session_id="probe",
        telemetry=telemetry, total_prompt_tokens=80,
    )
    episode_id = memory.store_temporal_episode(
        "Cedar escalation team is ORANGE.", topic_key="cedar::team", action="set",
        importance=1.0, bypass_filter=True,
    )

    result = memory.build_prompt(
        "Which team handles Cedar escalations?", reserve_output_tokens=20, return_trace=True,
    )

    evidence = next(item for item in result["trace"].evidence if item.source == "episodic")
    assert evidence.meta["episode_id"] == episode_id
    assert evidence.meta["topic_key"] == "cedar::team"
    assert result["budget_diagnostics"]["memory_candidate_count"] >= 1
    assert result["budget_diagnostics"]["memory_included_count"] >= 1
    assert result["retrieval_diagnostics"]["temporal_filtered_count"] == 0
    assert any(event.event_type == "prompt_budget_completed" for event in events)
