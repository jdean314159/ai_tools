from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import pytest
from pydantic import BaseModel

from language_tutor.engine_manager import EngineManager
from language_tutor.hardware_strategy import STRATEGIES
from language_tutor.tutor_session import TutorSession


class FakeStructuredPlan(BaseModel):
    warmup_topic: str = "daily life"
    focus_areas: list[str] = ["ser vs estar", "present progressive"]
    drill_type: str = "mixed_review"
    new_content: list[str] = ["mercado", "ayer"]
    estimated_minutes: dict[str, int] = {"warmup": 5, "conversation": 7, "drill": 3}


class RecordingEngine:
    def __init__(self, *, purpose: str, session_summary: str | None = None) -> None:
        self.purpose = purpose
        self.session_summary = session_summary or "Session summary: practiced ser vs estar and present progressive."
        self.prompts: list[str] = []
        self.structured_prompts: list[str] = []
        self.responses: list[str] = []

    def generate_structured(self, prompt: str, response_model: type[BaseModel], **kwargs):
        del kwargs
        self.structured_prompts.append(prompt)
        return response_model(**FakeStructuredPlan().model_dump())

    def generate(self, prompt: str, **kwargs) -> str:
        del kwargs
        self.prompts.append(prompt)
        if self.purpose == "planning":
            return self.session_summary

        idx = len(self.responses)
        if idx == 0:
            response = "Corrección: di 'estoy estudiando español', no 'yo soy estudiando español'."
        else:
            response = f"Seguimos hablando. Turno {idx + 1}."
        self.responses.append(response)
        return response

    def count_tokens(self, text: str) -> int:
        return max(1, len((text or "").split())) if (text or "").strip() else 0

    def generate_with_logprobs(self, prompt: str, **kwargs):
        text = self.generate(prompt, **kwargs)
        return text, [-0.1] * max(1, len(text.split()))


@pytest.fixture
def local_strategy() -> dict:
    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    strategy["planner"]["model"] = "test-planner"
    strategy["executor"]["model"] = "test-executor"
    return strategy


@pytest.fixture
def recording_loader(monkeypatch: pytest.MonkeyPatch):
    engines: dict[str, list[RecordingEngine]] = {"planning": [], "execution": []}

    def _load_engine(self: EngineManager, config: dict, purpose: str):
        del config
        engine = RecordingEngine(purpose=purpose)
        engines[purpose].append(engine)
        return engine

    monkeypatch.setattr(EngineManager, "_load_engine", _load_engine)
    return engines


def _build_session(tmp_path: Path, strategy: dict, *, memory_backend: str, session_id: str) -> TutorSession:
    return TutorSession(
        language="spanish",
        strategy=strategy,
        base_dir=tmp_path,
        session_id=session_id,
        memory_backend=memory_backend,
    )


@pytest.mark.parametrize("memory_backend", ["engram_lite", "engram"])
def test_recent_turns_and_correction_carry_forward_reach_next_prompt(
    tmp_path: Path,
    local_strategy: dict,
    recording_loader,
    memory_backend: str,
):
    session = _build_session(tmp_path, local_strategy, memory_backend=memory_backend, session_id=f"carry_{memory_backend}")
    try:
        asyncio.run(session.start(duration_minutes=15))
        asyncio.run(session.handle_text("Yo soy estudiando español."))
        asyncio.run(session.handle_text("Hoy quiero practicar otra vez."))

        executor = recording_loader["execution"][0]
        assert len(executor.prompts) >= 2
        second_prompt = executor.prompts[-1]

        assert "Yo soy estudiando español." in second_prompt
        assert "estoy estudiando español" in second_prompt
    finally:
        session.close()


@pytest.mark.parametrize("memory_backend", ["engram_lite", "engram"])
def test_session_restart_resume_surfaces_previous_summary_and_recent_turns(
    tmp_path: Path,
    local_strategy: dict,
    recording_loader,
    memory_backend: str,
):
    session_id = f"resume_{memory_backend}"
    first = _build_session(tmp_path, local_strategy, memory_backend=memory_backend, session_id=session_id)
    try:
        asyncio.run(first.start(duration_minutes=12))
        asyncio.run(first.handle_text("Ayer fui al mercado."))
        summary = asyncio.run(first.end_session())["summary"]
        assert "Session summary:" in summary
    finally:
        first.close()

    second = _build_session(tmp_path, local_strategy, memory_backend=memory_backend, session_id=session_id)
    try:
        recent_turns = second.memory.get_recent_turns(n=10)
        assert recent_turns
        assert any("mercado" in turn.content.lower() for turn in recent_turns)

        asyncio.run(second.start(duration_minutes=12))
        planner = recording_loader["planning"][-1]
        planning_prompt = planner.structured_prompts[-1]
        assert "Previous sessions:" in planning_prompt
        assert "Session summary: practiced ser vs estar and present progressive." in planning_prompt
    finally:
        second.close()


@pytest.mark.parametrize("memory_backend", ["engram_lite", "engram"])
def test_longer_session_prompt_building_compresses_when_budget_is_tight(
    tmp_path: Path,
    local_strategy: dict,
    recording_loader,
    memory_backend: str,
):
    session = _build_session(tmp_path, local_strategy, memory_backend=memory_backend, session_id=f"compress_{memory_backend}")
    try:
        asyncio.run(session.start(duration_minutes=10))
        for idx in range(12):
            session.memory.add_turn("user", f"usuario turno {idx} " + ("palabra " * 8))
            session.memory.add_turn("assistant", f"asistente turno {idx} " + ("respuesta " * 8))

        result = session.memory.build_prompt(
            user_message="Cuéntame qué recuerdas de nuestra práctica.",
            max_prompt_tokens=160,
            reserve_output_tokens=20,
        )

        assert result["prompt_tokens"] <= 160
        assert result["compressed"] is True
        assert result["memory_tokens"] > 0
    finally:
        session.close()
