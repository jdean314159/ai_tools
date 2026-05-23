from engram import ProjectMemory, trace_to_memory_records


def test_project_memory_exposes_shared_descriptor() -> None:
    memory = ProjectMemory(session_id="s1")
    descriptor = memory.describe_component()

    assert descriptor.provider == "engram"
    assert descriptor.supports("prompt_augmentation")
    assert descriptor.kind.value == "memory"


def test_prompt_trace_converts_to_interop_events_and_memory_records() -> None:
    memory = ProjectMemory(session_id="s1")
    memory.store_episode("Remember the Fibonacci exercise.", importance=0.9)

    trace = memory.build_prompt_trace("Tell me more about the exercise.")
    events = trace.to_interop_events()
    records = trace_to_memory_records(trace)

    assert events
    assert events[0].event_type == "prompt_build_completed"
    assert all(event.source_package == "engram" for event in events)
    assert isinstance(records, list)
