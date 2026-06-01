from __future__ import annotations

import os
import threading
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ._bootstrap import install_repo_source_paths

install_repo_source_paths()

from llm_engines import get_engine

from .drills import DrillSystem
from .profiles import get_profile
from .session import LanguageTutor
from .store import TutorStore
from .stub_engine import StubTutorEngine

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - exercised by direct CLI use
    raise RuntimeError(
        "The graphical language tutor requires FastAPI. Run `make install` from "
        "the repo root, or install the language_tutor package extras."
    ) from exc


APP_DIR = Path(__file__).resolve().parent
DEFAULT_BASE_DIR = Path(os.getenv("LANGUAGE_TUTOR_EXAMPLE_DATA", ".language_tutor_example"))

app = FastAPI(
    title="Public API Language Tutor Example",
    description="Graphical language tutor built from public ai_tools APIs.",
    version="0.1.0",
)

_sessions: dict[str, LanguageTutor] = {}
_lock = threading.Lock()


class StartRequest(BaseModel):
    language: str = "spanish"
    duration_minutes: int = 30
    backend: str = "ollama"
    model: str = "qwen3:8b"
    base_dir: str | None = None


class MessageRequest(BaseModel):
    session_id: str
    message: str


class ExplainRequest(BaseModel):
    session_id: str
    text: str
    question: str | None = None


class LookupRequest(BaseModel):
    session_id: str
    word: str
    context: str | None = None


class CheckTextRequest(BaseModel):
    session_id: str
    text: str


class DrillRequest(BaseModel):
    session_id: str
    drill_type: str = "auto"


class DrillCheckRequest(BaseModel):
    session_id: str
    answer: str


class ImportVocabularyRequest(BaseModel):
    session_id: str
    text: str


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if is_dataclass(value):
        return _plain(asdict(value))
    if hasattr(value, "__dict__"):
        return {key: _plain(item) for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


def _get_session(session_id: str) -> LanguageTutor:
    with _lock:
        session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _build_engine(backend: str, model: str):
    normalized = (backend or "stub").strip().lower()
    if normalized == "stub":
        return StubTutorEngine()
    return get_engine(normalized, model)


def _store() -> TutorStore:
    return TutorStore(DEFAULT_BASE_DIR / "sessions.sqlite")


def _close_language_sessions(language: str) -> None:
    with _lock:
        closing = [
            _sessions.pop(session_id)
            for session_id, tutor in list(_sessions.items())
            if tutor.language == language
        ]
    for tutor in closing:
        tutor.close()


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (APP_DIR / "web_index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "examples.language_tutor"}


@app.post("/api/session/start")
async def start_session(request: StartRequest) -> dict[str, Any]:
    try:
        language = get_profile(request.language).code
        engine = _build_engine(request.backend, request.model)
        _close_language_sessions(language)
        tutor = LanguageTutor(
            language=language,
            engine=engine,
            base_dir=Path(request.base_dir) if request.base_dir else DEFAULT_BASE_DIR,
        )
        result = tutor.start_session(duration_minutes=request.duration_minutes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    with _lock:
        _sessions[tutor.session_id] = tutor
    return {
        **_plain(result),
        "backend": request.backend,
        "model": request.model,
        "capability": _plain(tutor.capability_descriptor()),
    }


@app.post("/api/conversation/message")
async def send_message(request: MessageRequest) -> dict[str, Any]:
    session = _get_session(request.session_id)
    response = session.send_message(request.message)
    return {"session_id": request.session_id, **_plain(response)}


@app.post("/api/session/end")
async def end_session(request: MessageRequest) -> dict[str, Any]:
    session = _get_session(request.session_id)
    result = session.end_session()
    with _lock:
        _sessions.pop(request.session_id, None)
    session.close()
    return _plain(result)


@app.get("/api/session/metrics/{session_id}")
async def metrics(session_id: str) -> dict[str, Any]:
    return _plain(_get_session(session_id).metrics())


@app.get("/api/session/memory/{session_id}")
async def memory(session_id: str) -> dict[str, Any]:
    return _plain(_get_session(session_id).memory_snapshot())


@app.get("/api/session/history/{language}")
async def history(language: str, limit: int = 10) -> dict[str, Any]:
    language_code = get_profile(language).code
    return _plain({"language": language_code, "sessions": _store().history(language_code, limit)})


@app.get("/api/session/stats/{language}")
async def stats(language: str) -> dict[str, Any]:
    language_code = get_profile(language).code
    return _plain({"language": language_code, "stats": _store().stats(language_code)})


@app.post("/api/conversation/explain")
async def explain(request: ExplainRequest) -> dict[str, Any]:
    explanation = _get_session(request.session_id).explain(request.text, request.question)
    return {"text": request.text, "question": request.question, "explanation": explanation}


@app.post("/api/conversation/lookup")
async def lookup(request: LookupRequest) -> dict[str, Any]:
    return _plain(_get_session(request.session_id).lookup(request.word, request.context))


@app.post("/api/conversation/check")
async def check_text(request: CheckTextRequest) -> dict[str, Any]:
    return _plain(_get_session(request.session_id).check_text(request.text))


@app.get("/api/conversation/drill/types")
async def drill_types(language: str = "spanish") -> dict[str, Any]:
    language_code = get_profile(language).code
    return _plain({"language": language_code, "types": DrillSystem(language_code, _store()).types()})


@app.post("/api/conversation/drill")
async def drill(request: DrillRequest) -> dict[str, Any]:
    return _plain(_get_session(request.session_id).get_drill(request.drill_type))


@app.post("/api/conversation/drill/check")
async def drill_check(request: DrillCheckRequest) -> dict[str, Any]:
    return _plain(_get_session(request.session_id).check_drill(request.answer))


@app.post("/api/conversation/import/vocabulary")
async def import_vocabulary(request: ImportVocabularyRequest) -> dict[str, Any]:
    return _plain(_get_session(request.session_id).import_vocabulary(request.text))


def main() -> None:
    import uvicorn

    host = os.getenv("LANGUAGE_TUTOR_EXAMPLE_HOST", "127.0.0.1")
    port = int(os.getenv("LANGUAGE_TUTOR_EXAMPLE_PORT", "8090"))
    uvicorn.run("examples.language_tutor.web_app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
