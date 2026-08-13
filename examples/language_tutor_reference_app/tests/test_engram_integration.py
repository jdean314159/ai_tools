from __future__ import annotations

import asyncio
import copy
import os
from pathlib import Path

import pytest
from pydantic import BaseModel

from language_tutor.engine_manager import EngineManager
from language_tutor.hardware_strategy import STRATEGIES
from language_tutor.tutor_session import SessionState, TutorSession


class FakeStructuredPlan(BaseModel):
    warmup_topic: str = "daily life"
    focus_areas: list[str] = ["past tense", "articles"]
    drill_type: str = "mixed_review"
    new_content: list[str] = ["mercado", "ayer"]
    estimated_minutes: dict[str, int] = {"warmup": 5, "conversation": 7, "drill": 3}


class FakeEngine:
    def __init__(self, *, purpose: str = "execution", model_name: str = "fake-model") -> None:
        self.purpose = purpose
        self.model_name = model_name
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        self.calls.append(
            {
                "kind": "generate",
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self.purpose == "planning":
            return "Session summary: practiced past tense and vocabulary."
        return "Claro. Ayer fui al mercado y compré comida. ¿Qué hiciste tú?"

    def generate_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> BaseModel:
        self.calls.append(
            {
                "kind": "generate_structured",
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_model": response_model,
            }
        )
        return response_model(**FakeStructuredPlan().model_dump())

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
    engines: list[tuple[str, str]] = []

    def _load_engine(self: EngineManager, config: dict, purpose: str):
        engines.append((purpose, config["engine"]))
        return FakeEngine(purpose=purpose, model_name=config.get("model", "fake"))

    monkeypatch.setattr(EngineManager, "_load_engine", _load_engine)
    return engines


def _build_session(
    tmp_path: Path,
    strategy: dict,
    memory_backend: str | None = None,
) -> TutorSession:
    return TutorSession(
        language="spanish",
        strategy=strategy,
        base_dir=tmp_path,
        session_id=f"test_session_{memory_backend or 'default'}",
        memory_backend=memory_backend,
    )


def test_language_tutor_package_imports_without_optional_cloud_sdks():
    import language_tutor
    import language_tutor.engine_manager
    import language_tutor.hardware_strategy
    import language_tutor.tutor_session

    assert language_tutor.TutorSession is TutorSession
    assert "local_everything" in language_tutor.STRATEGIES


def test_default_memory_backend_is_engram(tmp_path: Path, local_strategy: dict, fake_engine_loader):
    session = _build_session(tmp_path, local_strategy)
    try:
        assert session.memory_backend == "engram"
        assert session.memory.backend_name == "engram"
    finally:
        try:
            session.close()
        except Exception:
            pass


def test_strategy_catalogue_exposes_cross_library_modes():
    required = {
        "local_everything",
        "hybrid_cloud_planning",
        "cloud_executor_only",
        "cloud_everything",
        "gemini_planning",
        "gemini_local_3b",
        "gemini_everything",
        "openai_planning",
        "openai_local_3b",
        "openai_everything",
    }
    assert required.issubset(STRATEGIES)
    assert STRATEGIES["gemini_planning"]["planner"]["engine"] == "gemini"
    assert STRATEGIES["openai_planning"]["planner"]["engine"] == "openai"


def test_engine_manager_gemini_missing_key_raises_runtimeerror(local_strategy: dict, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    manager = EngineManager(local_strategy)
    with pytest.raises(RuntimeError, match="Cannot initialize"):
        manager._load_engine({"engine": "gemini", "model": "gemini-2.0-flash"}, "planning")


@pytest.mark.parametrize("memory_backend", ["engram"])
def test_tutor_session_round_trip_exercises_selected_memory_backend(
    tmp_path: Path,
    local_strategy: dict,
    fake_engine_loader,
    memory_backend: str,
):
    session = _build_session(tmp_path, local_strategy, memory_backend=memory_backend)
    try:
        start_result = asyncio.run(session.start(duration_minutes=15))
        assert start_result["session_id"] == f"test_session_{memory_backend}"
        assert session.current_plan is not None
        assert session.state == SessionState.WARMUP
        assert session.memory.backend_name == memory_backend

        response = asyncio.run(session.handle_text("Hola, yo soy estudiando español ahora mismo."))
        assert response.text
        assert isinstance(response.new_vocabulary, list)
        assert isinstance(response.corrections, list)
        assert response.metadata is not None
        assert response.metadata["prompt_tokens"] >= 0

        summary_result = asyncio.run(session.end_session())
        assert summary_result["summary"].strip()
        assert summary_result["statistics"]["exchanges"] == 1
        assert session.state == SessionState.COMPLETED

        stats = session.memory.get_stats()
        working = stats.get("working", {})
        assert working.get("message_count", 0) >= 2

        weaknesses = session.store.get_weaknesses("spanish")
        assert isinstance(weaknesses, list)

        assert ("execution", "ollama") in fake_engine_loader
        assert ("planning", "ollama") in fake_engine_loader
    finally:
        try:
            session.close()
        except Exception:
            pass


def test_tutor_session_can_drive_llm_engines_adapter_path(tmp_path: Path, local_strategy: dict, monkeypatch: pytest.MonkeyPatch):
    built: list[tuple[str, str]] = []

    def fake_build_engine(config: dict):
        built.append((config["engine"], config["model"]))
        purpose = "planning" if config is planner_config else "execution"
        return FakeEngine(purpose=purpose, model_name=config["model"])

    planner_config = local_strategy["planner"]
    executor_config = local_strategy["executor"]

    # llm_engines is now the default; no env var needed
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)
    monkeypatch.setattr("language_tutor.llm_engines_adapter.build_engine", fake_build_engine)

    session = TutorSession(
        language="spanish",
        strategy=local_strategy,
        base_dir=tmp_path,
        session_id="adapter_session",
    )
    try:
        start_result = asyncio.run(session.start(duration_minutes=10))
        assert start_result["session_id"] == "adapter_session"
        result = asyncio.run(session.handle_text("Ayer fui al mercado."))
        assert result.text
        assert session.memory_backend == "engram"
        assert built == [
            (executor_config["engine"], executor_config["model"]),
            (planner_config["engine"], planner_config["model"]),
        ]
    finally:
        try:
            session.close()
        except Exception:
            pass



@pytest.mark.skipif(not os.getenv("LANGUAGE_TUTOR_LIVE_OLLAMA"), reason="set LANGUAGE_TUTOR_LIVE_OLLAMA=1 for live Ollama integration")
def test_live_ollama_smoke(tmp_path: Path):
    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    session = TutorSession(
        language="spanish",
        strategy=strategy,
        base_dir=tmp_path,
        session_id="live_ollama_session",
    )
    try:
        response = asyncio.run(session.handle_text("Hola. ¿Cómo estás hoy?"))
        assert response.text.strip()
        assert session.memory_backend == "engram"
    finally:
        try:
            session.close()
        except Exception:
            pass
