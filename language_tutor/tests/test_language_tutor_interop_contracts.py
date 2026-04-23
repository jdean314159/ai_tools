from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import pytest
from llm_harness_core import CapabilityDescriptor, MemoryRecord, OperationResult, TraceEvent

from language_tutor.hardware_strategy import STRATEGIES
from language_tutor.tutor_session import TutorSession


class FakeEngine:
    def __init__(self, *, purpose: str = "execution", model_name: str = "fake-model") -> None:
        self.purpose = purpose
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: str | None = None, max_tokens: int = 512, temperature: float = 0.7) -> str:
        del prompt, system_prompt, max_tokens, temperature
        if self.purpose == "planning":
            return "Session summary: practiced past tense and vocabulary."
        return "Claro. Ayer fui al mercado y compré comida. ¿Qué hiciste tú?"

    def generate_structured(self, prompt: str, response_model, system_prompt: str | None = None, max_tokens: int = 1024, temperature: float = 0.0):
        del prompt, system_prompt, max_tokens, temperature
        return response_model(
            warmup_topic="daily life",
            focus_areas=["past tense", "articles"],
            drill_type="mixed_review",
            new_content=["mercado", "ayer"],
            estimated_minutes={"warmup": 5, "conversation": 7, "drill": 3},
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))


@pytest.fixture
def local_strategy() -> dict:
    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    strategy["planner"]["model"] = "test-planner"
    strategy["executor"]["model"] = "test-executor"
    return strategy


@pytest.fixture
def fake_engine_loader(monkeypatch: pytest.MonkeyPatch):
    from language_tutor.engine_manager import EngineManager

    def _load_engine(self: EngineManager, config: dict, purpose: str):
        return FakeEngine(purpose=purpose, model_name=config.get("model", "fake"))

    monkeypatch.setattr(EngineManager, "_load_engine", _load_engine)


def _build_session(tmp_path: Path, strategy: dict, memory_backend: str | None = None) -> TutorSession:
    return TutorSession(
        language="spanish",
        strategy=strategy,
        base_dir=tmp_path,
        session_id=f"interop_{memory_backend or 'default'}",
        memory_backend=memory_backend,
    )


def test_capability_descriptor_is_shared_contract(tmp_path: Path, local_strategy: dict, fake_engine_loader):
    session = _build_session(tmp_path, local_strategy)
    try:
        descriptor = session.get_capability_descriptor()
        assert isinstance(descriptor, CapabilityDescriptor)
        assert descriptor.provider == "language_tutor"
        assert descriptor.component == "TutorSession"
        assert f"memory_backend:{session.memory_backend}" in descriptor.features
    finally:
        session.close()


@pytest.mark.parametrize("memory_backend", ["engram_lite", "engram"])
def test_start_interop_returns_operation_result_with_shared_diagnostics(tmp_path: Path, local_strategy: dict, fake_engine_loader, memory_backend: str):
    session = _build_session(tmp_path, local_strategy, memory_backend=memory_backend)
    try:
        result = asyncio.run(session.start_interop(duration_minutes=15))
        assert isinstance(result, OperationResult)
        assert result.ok is True
        assert result.value["session_id"] == f"interop_{memory_backend}"
        assert isinstance(result.diagnostics.get("capability"), CapabilityDescriptor)
        assert all(isinstance(evt, TraceEvent) for evt in result.diagnostics.get("trace_events", ()))
        assert all(isinstance(rec, MemoryRecord) for rec in result.diagnostics.get("memory_records", ()))
        assert result.diagnostics["trace_events"][0].event_type == "language_tutor.session.started"
    finally:
        session.close()


@pytest.mark.parametrize("memory_backend", ["engram_lite", "engram"])
def test_handle_text_interop_returns_shared_contract_result(tmp_path: Path, local_strategy: dict, fake_engine_loader, memory_backend: str):
    session = _build_session(tmp_path, local_strategy, memory_backend=memory_backend)
    try:
        asyncio.run(session.start(duration_minutes=15))
        result = asyncio.run(session.handle_text_interop("Hola, yo soy estudiando español ahora mismo."))
        assert isinstance(result, OperationResult)
        assert result.ok is True
        assert result.value["text"]
        assert isinstance(result.diagnostics.get("capability"), CapabilityDescriptor)
        assert result.diagnostics["trace_events"][0].event_type == "language_tutor.turn.completed"
        assert all(isinstance(rec, MemoryRecord) for rec in result.diagnostics.get("memory_records", ()))
    finally:
        session.close()


def test_explain_interop_returns_shared_contract_result(tmp_path: Path, local_strategy: dict, fake_engine_loader):
    session = _build_session(tmp_path, local_strategy)
    try:
        result = asyncio.run(session.explain_interop("Ayer fui al mercado.", "Why is fui used here?"))
        assert isinstance(result, OperationResult)
        assert result.ok is True
        assert "explanation" in result.value
        assert result.diagnostics["trace_events"][0].event_type == "language_tutor.explanation.completed"
    finally:
        session.close()
