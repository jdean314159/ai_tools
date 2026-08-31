from __future__ import annotations

from llm_inspector_ui import describe_ui
from llm_inspector_ui.interop import artifact_to_operation_result
from llm_inspector_ui.state.models import RunArtifact
from llm_inspector_ui.utils.capability_access import capability_to_row
from llm_inspector_ui.utils.trace_access import get_events

from datetime import datetime, timezone


def test_describe_ui_returns_shared_capability_descriptor():
    descriptor = describe_ui()
    assert descriptor.provider == "llm_inspector_ui"
    assert descriptor.kind == "ui" or str(descriptor.kind).endswith("UI")

    row = capability_to_row(descriptor)
    assert row["component"] == "LLMInspectorUI"
    assert "trace_visualization" in row["features"]


def test_trace_access_normalizes_interop_events():
    trace = {
        "events": [
            {
                "event_type": "memory_retrieved",
                "source_package": "engram",
                "source_component": "ProjectMemory",
                "payload": {"count": 2},
                "severity": "info",
                "message": "Retrieved memory.",
                "tags": ["memory", "retrieval"],
            }
        ]
    }

    events = get_events(trace)
    assert events[0]["kind"] == "memory_retrieved"
    assert events[0]["fields"] == {"count": 2}
    assert events[0]["source_package"] == "engram"
    assert events[0]["tags"] == ("memory", "retrieval")


def test_artifact_to_operation_result_uses_serialized_trace():
    artifact = RunArtifact(
        run_id="run-1",
        session_id="sess-1",
        turn_id="turn-1",
        assistant_turn_id=None,
        created_at=datetime.now(timezone.utc),
        engine_id="echo",
        model_id="echo",
        augmenter_id="baseline",
        mode="chat",
        trace={"turn": {"role": "user", "text": "hello", "session_id": "sess-1"}},
    )

    result = artifact_to_operation_result(artifact)
    assert result.ok is True
    assert result.value["turn"]["text"] == "hello"
    assert result.diagnostics["augmenter_id"] == "baseline"
