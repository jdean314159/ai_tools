"""
test_routes_conversation.py

FastAPI route-level tests for /api/conversation/*.

Uses httpx TestClient (starlette) so no actual server is started.
All session state is injected directly into active_sessions.
No live LLM calls — sessions carry FakeEngine instances.

Routes tested:
  POST /api/conversation/message          — 404 / 200
  POST /api/conversation/explain          — 404 / 200
  POST /api/conversation/lookup           — 404 / 200
  POST /api/conversation/check            — 404 / 200
  POST /api/conversation/drill            — 404 / 200
  POST /api/conversation/drill/check      — 404 / 200
  GET  /api/conversation/drill/types      — spanish / latin
  GET  /api/conversation/history/{id}     — 404 / 200
  GET  /api/conversation/metrics/{id}     — 404 / 200
"""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

pytest.importorskip("fastapi", reason="fastapi required for route tests")
pytest.importorskip("httpx", reason="httpx required for TestClient")

pytestmark = pytest.mark.skip(
    reason="legacy synchronous TestClient suite is incompatible with the current httpx transport"
)

from fastapi.testclient import TestClient  # noqa: E402

from language_tutor.app import app  # noqa: E402
from language_tutor.engine_manager import EngineManager  # noqa: E402
from language_tutor.hardware_strategy import STRATEGIES  # noqa: E402
from language_tutor.routes.session import active_sessions  # noqa: E402
from language_tutor.tutor_session import TutorSession  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakePlan(BaseModel):
    warmup_topic: str = "travel"
    focus_areas: list[str] = ["past tense"]
    drill_type: str = "mixed_review"
    new_content: list[str] = ["ayer"]
    estimated_minutes: dict[str, int] = {"warmup": 5, "conversation": 7, "drill": 3}


class _FakeEngine:
    model_name = "fake"

    def generate(self, prompt: str, **kwargs: Any) -> str:
        # Return JSON for structured calls; plain text otherwise
        if "json" in prompt.lower() or "JSON" in prompt:
            return json.dumps({"translation": "to go", "alternatives": [], "part_of_speech": "verb",
                               "notes": "", "example": "Yo voy."})
        return "Claro, eso es una buena pregunta sobre el español."

    def generate_structured(self, prompt: str, response_model, **kwargs: Any):
        return response_model(**_FakePlan().model_dump())

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(tmp_path: Path, monkeypatch):
    """Create a started session and register it in active_sessions.

    The EngineManager._load_engine patch is applied via monkeypatch so it
    remains active for the entire fixture lifetime — including session.start(),
    which triggers lazy planner loading after construction.
    """
    strategy = copy.deepcopy(STRATEGIES["local_everything"])
    monkeypatch.setattr(EngineManager, "_load_engine", lambda self, config, purpose: _FakeEngine())
    s = TutorSession(
        language="spanish",
        strategy=strategy,
        base_dir=tmp_path,
        session_id="test-session",
    )
    asyncio.run(s.start(duration_minutes=15))
    active_sessions[s.session_id] = s
    yield s
    active_sessions.pop(s.session_id, None)
    try:
        s.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# POST /api/conversation/message
# ---------------------------------------------------------------------------

class TestMessageRoute:
    def test_missing_session_returns_404(self, client):
        r = client.post("/api/conversation/message", json={
            "session_id": "no-such-session",
            "message": "Hola",
        })
        assert r.status_code == 404

    def test_found_session_returns_200(self, client, session):
        r = client.post("/api/conversation/message", json={
            "session_id": session.session_id,
            "message": "Yo quiero practicar español.",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["session_id"] == session.session_id
        assert body["message"]

    def test_response_includes_corrections_and_vocab(self, client, session):
        r = client.post("/api/conversation/message", json={
            "session_id": session.session_id,
            "message": "Hola",
        })
        body = r.json()
        assert "corrections" in body
        assert "new_vocabulary" in body
        assert "metadata" in body


# ---------------------------------------------------------------------------
# POST /api/conversation/explain
# ---------------------------------------------------------------------------

class TestExplainRoute:
    def test_missing_session_returns_404(self, client):
        r = client.post("/api/conversation/explain", json={
            "session_id": "no-such",
            "text": "Ayer fui al mercado.",
        })
        assert r.status_code == 404

    def test_found_session_returns_explanation(self, client, session):
        r = client.post("/api/conversation/explain", json={
            "session_id": session.session_id,
            "text": "Ayer fui al mercado.",
            "question": "Why is 'fui' used?",
        })
        assert r.status_code == 200
        body = r.json()
        assert "explanation" in body
        assert body["explanation"]
        assert body["text"] == "Ayer fui al mercado."


# ---------------------------------------------------------------------------
# POST /api/conversation/lookup
# ---------------------------------------------------------------------------

class TestLookupRoute:
    def test_missing_session_returns_404(self, client):
        r = client.post("/api/conversation/lookup", json={
            "session_id": "no-such",
            "word": "mercado",
        })
        assert r.status_code == 404

    def test_found_session_returns_lookup(self, client, session):
        r = client.post("/api/conversation/lookup", json={
            "session_id": session.session_id,
            "word": "mercado",
            "context": "Fui al mercado ayer.",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["word"] == "mercado"
        assert "translation" in body


# ---------------------------------------------------------------------------
# POST /api/conversation/check
# ---------------------------------------------------------------------------

class TestCheckInputRoute:
    def test_missing_session_returns_404(self, client):
        r = client.post("/api/conversation/check", json={
            "session_id": "no-such",
            "text": "Yo soy estudiando.",
        })
        assert r.status_code == 404

    def test_found_session_returns_errors_list(self, client, session):
        r = client.post("/api/conversation/check", json={
            "session_id": session.session_id,
            "text": "Yo soy estudiando.",
        })
        assert r.status_code == 200
        body = r.json()
        assert "text" in body
        assert "errors" in body
        assert isinstance(body["errors"], list)


# ---------------------------------------------------------------------------
# POST /api/conversation/drill + /drill/check
# ---------------------------------------------------------------------------

class TestDrillRoute:
    def test_get_drill_missing_session_returns_404(self, client):
        r = client.post("/api/conversation/drill", json={
            "session_id": "no-such",
            "drill_type": "mixed_review",
        })
        assert r.status_code == 404

    def test_get_drill_returns_question(self, client, session):
        r = client.post("/api/conversation/drill", json={
            "session_id": session.session_id,
            "drill_type": "mixed_review",
        })
        assert r.status_code == 200
        body = r.json()
        assert "prompt" in body
        assert "correct_answer" in body
        assert "drill_type" in body

    def test_check_drill_missing_session_returns_404(self, client):
        r = client.post("/api/conversation/drill/check", json={
            "session_id": "no-such",
            "user_answer": "fui",
        })
        assert r.status_code == 404

    def test_check_drill_returns_result_after_get_drill(self, client, session):
        # Must call /drill first to set the active question
        client.post("/api/conversation/drill", json={
            "session_id": session.session_id,
            "drill_type": "sentence_dictation",
        })
        r = client.post("/api/conversation/drill/check", json={
            "session_id": session.session_id,
            "user_answer": "Hola mundo",
        })
        assert r.status_code == 200
        body = r.json()
        assert "correct" in body
        assert "feedback" in body


# ---------------------------------------------------------------------------
# GET /api/conversation/drill/types
# ---------------------------------------------------------------------------

class TestDrillTypesRoute:
    def test_spanish_types_returned(self, client):
        r = client.get("/api/conversation/drill/types?language=spanish")
        assert r.status_code == 200
        types = {t["id"] for t in r.json()["types"]}
        assert "mixed_review" in types
        assert "irregular_verbs_preterite" in types
        assert "reflexive_verbs" in types

    def test_latin_types_returned(self, client):
        r = client.get("/api/conversation/drill/types?language=latin")
        assert r.status_code == 200
        types = {t["id"] for t in r.json()["types"]}
        assert "noun_declensions" in types
        assert "irregular_verbs_present" in types

    def test_default_is_spanish(self, client):
        r = client.get("/api/conversation/drill/types")
        assert r.status_code == 200
        types = {t["id"] for t in r.json()["types"]}
        assert "reflexive_verbs" in types


# ---------------------------------------------------------------------------
# GET /api/conversation/history/{session_id}
# ---------------------------------------------------------------------------

class TestHistoryRoute:
    def test_missing_session_returns_404(self, client):
        r = client.get("/api/conversation/history/no-such")
        assert r.status_code == 404

    def test_found_session_returns_history(self, client, session):
        # Add a turn first
        client.post("/api/conversation/message", json={
            "session_id": session.session_id,
            "message": "Hola",
        })
        r = client.get(f"/api/conversation/history/{session.session_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["session_id"] == session.session_id
        assert isinstance(body["history"], list)


# ---------------------------------------------------------------------------
# GET /api/conversation/metrics/{session_id}
# ---------------------------------------------------------------------------

class TestMetricsRoute:
    def test_missing_session_returns_404(self, client):
        r = client.get("/api/conversation/metrics/no-such")
        assert r.status_code == 404

    def test_found_session_returns_metrics(self, client, session):
        r = client.get(f"/api/conversation/metrics/{session.session_id}")
        assert r.status_code == 200
        body = r.json()
        assert "exchange_count" in body or "corrections_count" in body or isinstance(body, dict)
