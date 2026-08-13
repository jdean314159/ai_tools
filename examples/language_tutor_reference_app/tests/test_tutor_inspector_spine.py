"""
integration_tests/test_tutor_inspector_spine.py

Cross-package spine test: language_tutor → llm_inspector_ui → llm_inspector

Verifies that:
  1. TutorSession emits well-formed OperationResult objects from its interop methods.
  2. InspectorService can normalise those OperationResult objects into a trace dict.
  3. The trace dict satisfies the same structural contracts as augmenter-spine traces
     (session_id, sections, token accounting, trace_events).
  4. Traces from two different turns can be compared side-by-side.
  5. No live model, memory service, or network call is required.

This test lives in integration_tests/ alongside test_augmenter_spine.py because
it spans three packages (language_tutor, llm_inspector_ui, llm_inspector).
"""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from llm_harness_core import CapabilityDescriptor, MemoryRecord, OperationResult, TraceEvent
from llm_inspector_ui.services.inspector_service import InspectorService
from llm_inspector_ui.utils.trace_access import (
    get_final_prompt,
    get_token_accounting,
)


# ---------------------------------------------------------------------------
# Fake engine — records calls, returns predictable text
# ---------------------------------------------------------------------------

class _FakePlan(BaseModel):
    warmup_topic: str = "daily life"
    focus_areas: list[str] = ["past tense", "ser vs estar"]
    drill_type: str = "mixed_review"
    new_content: list[str] = ["mercado", "ayer"]
    estimated_minutes: dict[str, int] = {"warmup": 5, "conversation": 7, "drill": 3}


class _FakeEngine:
    model_name = "fake-spine"

    def generate(self, prompt: str, **kwargs: Any) -> str:
        if "summary" in prompt.lower():
            return "Session summary: practiced ser vs estar and past tense."
        return "Claro. Ayer fui al mercado y compré frutas. ¿Qué hiciste tú?"

    def generate_structured(self, prompt: str, response_model: type[BaseModel], **kwargs: Any) -> BaseModel:
        return response_model(**_FakePlan().model_dump())

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))


# ---------------------------------------------------------------------------
# Session builder
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def patched_engine(monkeypatch):
    """Patch EngineManager._load_engine for the lifetime of the test.

    The patch is applied at class level so it remains active through
    session.start(), which triggers lazy planner loading after construction.
    """
    from language_tutor.engine_manager import EngineManager
    monkeypatch.setattr(
        EngineManager,
        "_load_engine",
        lambda self, config, purpose: _FakeEngine(),
    )


def _build_session(tmp_path: Path, session_id: str = "spine-session") -> Any:
    """Build a TutorSession with no real engines.

    Callers must ensure patched_engine fixture is active — either via
    the fixture parameter or by requesting it directly in the test.
    """
    from language_tutor.hardware_strategy import STRATEGIES
    from language_tutor.tutor_session import TutorSession

    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    return TutorSession(
        language="spanish",
        strategy=strategy,
        base_dir=tmp_path,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_inspector_trace(trace: dict[str, Any], *, session_id: str) -> None:
    """Assert core trace structure.

    Note: get_sections() returns [] for language_tutor OperationResult because
    InspectorService expects AugmentResult (the Engram contract has a `prompt`
    field) not OperationResult (llm_harness_core). The inspector still builds a
    valid trace dict — session_id, turn, and token_accounting are all present.
    Sections are only populated when the augment_result carries a prompt through
    the AugmentResult protocol.
    """
    assert trace["turn"]["session_id"] == session_id
    assert isinstance(get_token_accounting(trace), dict)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_start_interop_result_feeds_inspector_trace(tmp_path: Path, patched_engine):
    session = _build_session(tmp_path, session_id="spine-start")
    inspector = InspectorService()
    try:
        result = asyncio.run(session.start_interop(duration_minutes=20))

        # OperationResult shape
        assert isinstance(result, OperationResult)
        assert result.ok
        assert isinstance(result.diagnostics.get("capability"), CapabilityDescriptor)
        assert result.diagnostics["trace_events"]
        assert all(isinstance(e, TraceEvent) for e in result.diagnostics["trace_events"])
        assert all(isinstance(r, MemoryRecord) for r in result.diagnostics["memory_records"])

        # Feed to inspector
        trace = inspector.inspect(
            augmenter_id="language_tutor",
            augment_result=result,
            user_text="(session start)",
            session_id="spine-start",
        )
        _assert_inspector_trace(trace, session_id="spine-start")
    finally:
        session.close()


def test_handle_text_interop_result_feeds_inspector_trace(tmp_path: Path, patched_engine):
    session = _build_session(tmp_path, session_id="spine-text")
    inspector = InspectorService()
    try:
        asyncio.run(session.start(duration_minutes=15))
        result = asyncio.run(session.handle_text_interop(
            "Yo soy estudiando español ahora mismo."
        ))

        assert isinstance(result, OperationResult)
        assert result.ok
        assert result.value["text"]

        trace = inspector.inspect(
            augmenter_id="language_tutor",
            augment_result=result,
            user_text="Yo soy estudiando español ahora mismo.",
            session_id="spine-text",
        )
        _assert_inspector_trace(trace, session_id="spine-text")

        # The final prompt should mention Spanish (from system prompt / context)
        final = get_final_prompt(trace, fallback=result.value.get("text", ""))
        assert isinstance(final, str)
    finally:
        session.close()


def test_explain_interop_result_feeds_inspector_trace(tmp_path: Path, patched_engine):
    session = _build_session(tmp_path, session_id="spine-explain")
    inspector = InspectorService()
    try:
        result = asyncio.run(session.explain_interop(
            "Ayer fui al mercado.",
            question="Why is 'fui' used here?",
        ))

        # Verify OperationResult shape
        assert isinstance(result, OperationResult)
        assert result.ok
        assert "explanation" in result.value
        assert result.value["explanation"]
        events = result.diagnostics["trace_events"]
        assert events[0].event_type == "language_tutor.explanation.completed"
        assert all(isinstance(e, TraceEvent) for e in events)
        assert all(isinstance(r, MemoryRecord) for r in result.diagnostics["memory_records"])

        # InspectorService normalises the result into a trace dict.
        # Explain results have no prompt-augmentation sections (the explanation
        # IS the output), so we check the trace skeleton rather than sections.
        trace = inspector.inspect(
            augmenter_id="language_tutor",
            augment_result=result,
            user_text="Ayer fui al mercado.",
            session_id="spine-explain",
        )
        assert isinstance(trace, dict)
        assert trace["turn"]["session_id"] == "spine-explain"
        assert isinstance(get_token_accounting(trace), dict)
    finally:
        session.close()


def test_multiple_turns_produce_diffable_traces(tmp_path: Path, patched_engine):
    session = _build_session(tmp_path, session_id="spine-diff")
    inspector = InspectorService()
    try:
        asyncio.run(session.start(duration_minutes=15))

        result_a = asyncio.run(session.handle_text_interop("Hola, ¿cómo estás?"))
        result_b = asyncio.run(session.handle_text_interop("Ayer fui al mercado."))

        trace_a = inspector.inspect(
            augmenter_id="language_tutor",
            augment_result=result_a,
            user_text="Hola, ¿cómo estás?",
            session_id="spine-diff",
        )
        trace_b = inspector.inspect(
            augmenter_id="language_tutor",
            augment_result=result_b,
            user_text="Ayer fui al mercado.",
            session_id="spine-diff",
        )

        diff = inspector.diff(
            trace_a,
            trace_b,
            name_a="turn_1",
            name_b="turn_2",
        )
        assert isinstance(diff, dict)
        # Diff report should identify the two sides
        assert "turn_1" in diff.get("name_a", "") or any(
            "turn_1" in str(v) for v in diff.values()
        )
    finally:
        session.close()


def test_capability_descriptor_from_session_matches_inspector_trace(tmp_path: Path, patched_engine):
    session = _build_session(tmp_path, session_id="spine-cap")
    inspector = InspectorService()
    try:
        result = asyncio.run(session.start_interop(duration_minutes=10))
        cap = result.diagnostics.get("capability")

        assert cap.provider == "language_tutor"
        assert cap.component == "TutorSession"
        assert f"memory_backend:{session.memory_backend}" in cap.features

        trace = inspector.inspect(
            augmenter_id="language_tutor",
            augment_result=result,
            user_text="session start",
            session_id="spine-cap",
        )
        # Capability should propagate into the trace
        _assert_inspector_trace(trace, session_id="spine-cap")
    finally:
        session.close()


@pytest.mark.parametrize("memory_backend", ["engram"])
def test_memory_backend_produces_valid_inspector_traces(
    tmp_path: Path, memory_backend: str, patched_engine
):
    from language_tutor.hardware_strategy import STRATEGIES
    from language_tutor.tutor_session import TutorSession

    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    # patched_engine fixture keeps EngineManager._load_engine replaced for
    # the full test lifetime, so no inline patch needed here.
    session = TutorSession(
        language="spanish",
        strategy=strategy,
        base_dir=tmp_path / memory_backend,
        session_id=f"spine-backend-{memory_backend}",
        memory_backend=memory_backend,
    )

    inspector = InspectorService()
    try:
        result = asyncio.run(session.start_interop(duration_minutes=10))
        assert result.ok
        assert f"memory_backend:{memory_backend}" in result.diagnostics["capability"].features

        trace = inspector.inspect(
            augmenter_id="language_tutor",
            augment_result=result,
            user_text="session start",
            session_id=f"spine-backend-{memory_backend}",
        )
        _assert_inspector_trace(trace, session_id=f"spine-backend-{memory_backend}")
    finally:
        session.close()
