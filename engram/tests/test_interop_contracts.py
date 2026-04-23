from pathlib import Path

from llm_harness_core import CapabilityKind, MemoryRecord, OperationResult, TraceEvent

from engram import ProjectMemory, ProjectType
from engram.interop import describe_memory, trace_to_interop_events, trace_to_memory_records


class FakeEngine:
    backend_label = "fake"
    model_name = "fake-model"

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def generate(self, prompt: str) -> str:
        return "test reply"


def _make_memory(tmp_path: Path) -> ProjectMemory:
    return ProjectMemory(
        project_id="interop-test",
        project_type=ProjectType.GENERAL_ASSISTANT,
        base_dir=tmp_path,
        llm_engine=FakeEngine(),
    )


def test_describe_memory_returns_shared_capability_descriptor(tmp_path: Path):
    pm = _make_memory(tmp_path)
    descriptor = describe_memory(pm)
    assert descriptor.kind == CapabilityKind.MEMORY
    assert descriptor.provider == "engram"
    assert descriptor.component == "ProjectMemory"
    assert "trace_events" in descriptor.features
    assert descriptor.metadata["supports_canonical_updates"] is True
    pm.close()


def test_build_prompt_interop_returns_operation_result_with_shared_diagnostics(tmp_path: Path):
    pm = _make_memory(tmp_path)
    result = pm.build_prompt_interop("Remember that I prefer Python for scripts.")
    assert isinstance(result, OperationResult)
    assert result.ok is True
    assert isinstance(result.value, str)
    assert "Remember that I prefer Python" in result.value
    assert isinstance(result.diagnostics["trace_events"], list)
    assert isinstance(result.diagnostics["memory_records"], list)
    assert all(isinstance(event, TraceEvent) for event in result.diagnostics["trace_events"])
    assert all(isinstance(record, MemoryRecord) for record in result.diagnostics["memory_records"])
    pm.close()


def test_respond_interop_returns_answer_and_trace_metadata(tmp_path: Path):
    pm = _make_memory(tmp_path)
    result = pm.respond_interop("Hello there", query="Hello there")
    assert result.ok is True
    assert result.value == "test reply"
    assert result.diagnostics["prompt"]
    assert isinstance(result.diagnostics["trace_events"], list)
    assert any(event.event_type == "prompt_build_completed" for event in result.diagnostics["trace_events"])
    pm.close()


def test_prompt_trace_converts_to_shared_records_and_events(tmp_path: Path):
    pm = _make_memory(tmp_path)
    pm.add_turn("user", "Important: remember that I prefer Python over Java.")
    trace = pm.build_prompt_trace("What language do I prefer?", query="preferred language")
    records = trace_to_memory_records(trace)
    events = trace_to_interop_events(trace)
    assert isinstance(records, list)
    assert isinstance(events, list)
    assert all(isinstance(record, MemoryRecord) for record in records)
    assert all(isinstance(event, TraceEvent) for event in events)
    assert any(event.event_type == "memory_evidence_included" for event in events)
    pm.close()


def test_build_prompt_trace_preserves_evidence_metadata_for_interop(tmp_path: Path):
    pm = _make_memory(tmp_path)
    pm.add_turn("user", "Decision: use DuckDB for analytics.")
    trace = pm.build_prompt_trace("What database should analytics use?", query="analytics database")
    records = trace_to_memory_records(trace)
    assert trace.evidence
    assert any(record.metadata.get("origin") for record in records)
    assert any("preview" in record.metadata for record in records)
    events = trace_to_interop_events(trace)
    included = [event for event in events if event.event_type == "memory_evidence_included"]
    assert included
    assert any("provenance" in event.payload for event in included)
    assert any("transformations" in event.payload for event in included)
    pm.close()
