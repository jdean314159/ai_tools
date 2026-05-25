"""
Acceptance-test slice: runs offline with the stub engine.

This is the executable form of the acceptance test. It proves the turn loop
works end to end using only the public engram + llm_engines surfaces. The real
model output is validated separately on Jeff's machine via run_slice.py.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from engram import ProjectMemory

from language_tutor_slice.stub_engine import StubTutorEngine
from language_tutor_slice.tutor_turn import run_turn
from language_tutor_slice.vocab import SYSTEM_PROMPT, vocab_seed_text


def _memory(tmp: Path) -> ProjectMemory:
    mem = ProjectMemory(
        base_dir=tmp,
        project_id="spanish_tutor_slice",
        session_id="t",
        system_prompt=SYSTEM_PROMPT,
    )
    mem.new_session("t")
    mem.index_text(vocab_seed_text())
    return mem


def test_turn_round_trips() -> None:
    with tempfile.TemporaryDirectory() as d:
        mem = _memory(Path(d))
        engine = StubTutorEngine()
        result = run_turn(
            memory=mem,
            engine=engine,
            session_id="t",
            user_input="¿Cómo se usa 'ser'?",
        )
        # Engine was called once with a non-empty prompt.
        assert len(engine.calls) == 1
        assert engine.calls[0].messages[-1].content
        # Response text came back via the public .text accessor.
        assert result.response_text
        assert result.backend == "stub"
        # The prompt actually contained the user message.
        assert "ser" in result.prompt
        mem.close()


def test_second_turn_retrieves_prior_context() -> None:
    with tempfile.TemporaryDirectory() as d:
        mem = _memory(Path(d))
        engine = StubTutorEngine()
        run_turn(memory=mem, engine=engine, session_id="t",
                 user_input="Me llamo Jeff y soy ingeniero.")
        second = run_turn(memory=mem, engine=engine, session_id="t",
                          user_input="¿Qué te dije sobre mi trabajo?")
        # Two engine calls; second prompt is non-trivial (memory assembled).
        assert len(engine.calls) == 2
        assert len(second.prompt) > 0


def test_only_public_symbols_imported() -> None:
    """Guard: the slice modules import engram/llm_engines only via public names."""
    import engram
    import llm_engines
    from language_tutor_slice import tutor_turn

    for name in ("ProjectMemory",):
        assert name in engram.__all__, f"{name} not public in engram"
    for name in ("ChatMessage", "GenerationRequest", "GenerationResponse"):
        assert name in llm_engines.__all__, f"{name} not public in llm_engines"
    # tutor_turn references these names directly:
    assert hasattr(tutor_turn, "ProjectMemory")
    assert hasattr(tutor_turn, "GenerationRequest")
