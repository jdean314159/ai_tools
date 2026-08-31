from __future__ import annotations

from llm_harness_core import CapabilityKind

from llm_inspector import (
    describe_inspector,
    report_to_operation_result,
    trace_to_interop_events,
    trace_to_memory_records,
    trace_to_operation_result,
)
from llm_inspector.augmenters import BaselineAugmenter
from llm_inspector.core import EvidenceItem, TraceEvent, Turn
from llm_inspector.inspectors import ContextInspector
from llm_inspector.protocols import AugmentRequest


def test_turn_and_evidence_convert_to_interop_objects() -> None:
    turn = Turn(role="user", text="hello", session_id="s1")
    msg = turn.to_interop_message()
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.metadata["session_id"] == "s1"

    evidence = EvidenceItem(
        text="prefers Spanish", source="episodic", score=0.9, meta={"title": "Preference"}
    )
    record = evidence.to_memory_record()
    doc = evidence.to_retrieved_document()
    assert record.source == "episodic"
    assert doc.title == "Preference"


def test_trace_event_compatibility_aliases() -> None:
    event = TraceEvent(
        event_type="memory_evidence_included",
        source_package="engram",
        source_component="PromptBuildTrace",
        payload={"source": "episodic"},
        message="Included episodic memory evidence.",
    )
    assert event.kind == "memory_evidence_included"
    assert event.fields["source"] == "episodic"


def test_inspector_interop_helpers() -> None:
    report = ContextInspector([BaselineAugmenter()]).run("hello world")
    trace = report.traces[0].trace

    descriptor = describe_inspector()
    assert descriptor.kind == CapabilityKind.INSPECTOR

    result = trace_to_operation_result(trace)
    assert result.ok is True
    assert result.diagnostics["metrics"]["engine"] == "baseline"

    records = trace_to_memory_records(trace)
    assert records == []

    events = trace_to_interop_events(trace)
    assert events == []

    report_result = report_to_operation_result(report)
    assert report_result.ok is True
    assert report_result.diagnostics["trace_count"] == 1


def test_augment_request_exposes_interop_message() -> None:
    req = AugmentRequest(
        turn=Turn(role="user", text="hello", session_id="s2"), query="hello", session_id="s2"
    )
    msg = req.to_interop_message()
    assert msg.role == "user"
    assert msg.metadata["session_id"] == "s2"
