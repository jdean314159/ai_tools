from __future__ import annotations

import asyncio
from pathlib import Path

from engram import __all__ as ENGRAM_PUBLIC
from llm_engines import __all__ as ENGINES_PUBLIC
from llm_harness_core import OperationResult

from .session import LanguageTutor
from .stub_engine import StubTutorEngine


def test_public_api_language_tutor_full_flow(tmp_path: Path) -> None:
    tutor = LanguageTutor(language="spanish", engine=StubTutorEngine(), base_dir=tmp_path, session_id="s1")
    try:
        started = tutor.start_session(duration_minutes=20)
        assert started["session_id"] == "s1"
        assert started["plan"]["focus_areas"]

        response = tutor.send_message("yo es estudiante")
        assert response.text
        assert response.corrections
        assert response.new_vocabulary
        assert any(call.max_tokens == 900 for call in tutor.engine.calls)
        assert tutor.metrics()["exchanges"] == 1

        explanation = tutor.explain("yo es estudiante", "Why is this wrong?")
        assert "soy" in explanation.lower()

        lookup = tutor.lookup("aprender")
        assert lookup["translation"]

        check = tutor.check_text("yo es estudiante")
        assert check["errors"]

        imported = tutor.import_vocabulary("viajar\nto travel\n\nlibro\nbook\n\nviajar\nto travel")
        assert imported["imported"] == 2

        drill = tutor.get_drill("vocabulary_review")
        checked = tutor.check_drill(drill["correct_answer"])
        assert checked["correct"] is True

        audio = tutor.handle_audio_transcript("yo es estudiante")
        assert audio["transcription"] == "yo es estudiante"

        pronunciation = tutor.score_pronunciation("Estoy aprendiendo espanol.", "Estoy aprendiendo espanol.")
        assert pronunciation["score"] == 100

        summary = tutor.end_session()
        assert summary["summary"]
        assert tutor.history()["sessions"]
        assert tutor.stats()["stats"]["sessions"] >= 1
        assert tutor.memory_snapshot()["turns"]

        interop = tutor.interop_result({"summary": summary["summary"]})
        assert isinstance(interop, OperationResult)
        assert interop.ok is True
        assert interop.diagnostics["trace_events"]
        assert interop.diagnostics["memory_records"]
        assert tutor.capability_descriptor().supports("conversation")
    finally:
        tutor.close()


def test_example_imports_public_ai_tools_surfaces() -> None:
    assert "ProjectMemory" in ENGRAM_PUBLIC
    assert "ChatModel" in ENGINES_PUBLIC
    assert "GenerationRequest" in ENGINES_PUBLIC


def test_graphical_app_stub_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LANGUAGE_TUTOR_EXAMPLE_DATA", str(tmp_path))

    from . import web_app

    html = (Path(web_app.__file__).resolve().parent / "web_index.html").read_text(encoding="utf-8")
    assert "Language Tutor" in html
    assert "/api/session/start" in html
    assert "/api/conversation/message" in html
    assert "contextmenu" in html
    assert "lookupPopup" in html
    assert any(route.path == "/api/session/start" for route in web_app.app.routes)

    first = asyncio.run(
        web_app.start_session(
            web_app.StartRequest(language="spanish", backend="stub", model="stub", base_dir=str(tmp_path))
        )
    )
    second = asyncio.run(
        web_app.start_session(
            web_app.StartRequest(language="spanish", backend="stub", model="stub", base_dir=str(tmp_path))
        )
    )
    try:
        assert first["session_id"] != second["session_id"]
        assert first["session_id"] not in web_app._sessions
        assert second["session_id"] in web_app._sessions
    finally:
        asyncio.run(web_app.end_session(web_app.MessageRequest(session_id=second["session_id"], message="")))
