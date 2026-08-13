"""
Session Management Routes

Endpoints for starting, ending, and checking session status.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from dataclasses import asdict
from pathlib import Path
import time
import threading

from language_tutor.tutor_session import TutorSession
from language_tutor.hardware_strategy import STRATEGIES, load_config
from language_tutor.session_store import SessionStore
from language_tutor.reference_stack import build_reference_stack

router = APIRouter()

# Global session storage (in-memory).
# Cleaned up by _reaper_thread when sessions are idle > SESSION_IDLE_TIMEOUT_S.
active_sessions = {}
_sessions_lock = threading.Lock()

SESSION_IDLE_TIMEOUT_S = 2 * 60 * 60   # 2 hours


def _reap_idle_sessions():
    """Close and remove sessions that have been idle for too long.

    Runs on a daemon thread so it never blocks the request path.
    """
    while True:
        time.sleep(300)  # check every 5 minutes
        now = time.time()
        to_close = []
        with _sessions_lock:
            for sid, session in list(active_sessions.items()):
                idle = now - getattr(session, "start_time", now)
                if idle > SESSION_IDLE_TIMEOUT_S:
                    to_close.append((sid, session))
            for sid, _ in to_close:
                del active_sessions[sid]
        for sid, session in to_close:
            try:
                session.close()
            except Exception:
                pass
            print(f"⏱  Reaped idle session {sid}")


# Start the reaper on module load (daemon=True so it won't block process exit)
_reaper = threading.Thread(target=_reap_idle_sessions, name="session-reaper", daemon=True)
_reaper.start()


class StartSessionRequest(BaseModel):
    """Request to start a new session."""
    language: str  # "spanish" or "latin"
    duration_minutes: Optional[int] = 30
    memory_backend: Optional[str] = None  # "engram"


class StartSessionResponse(BaseModel):
    """Response with session plan."""
    session_id: str
    language: str
    plan: dict
    greeting: str
    memory_backend: str
    voice_enabled: bool = False


class EndSessionRequest(BaseModel):
    """Request to end a session."""
    session_id: str


class EndSessionResponse(BaseModel):
    """Response with session summary."""
    session_id: str
    summary: str
    statistics: dict


class SessionStatusResponse(BaseModel):
    """Current session status."""
    session_id: str
    language: str
    state: str
    memory_backend: str
    active: bool


class ReferenceStackResponse(BaseModel):
    """Machine-readable description of the reference application stack."""
    app: str
    role: str
    learning_stage: str
    language: str
    memory_backend: str
    strategy: str
    required_packages: list[str]
    optional_packages: list[str]
    observability_packages: list[str]
    current_paths: dict
    future_paths: dict
    capability: dict


@router.post("/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    """
    Start a new tutoring session.

    This triggers:
    1. Load hardware strategy
    2. Initialize TutorSession
    3. Generate session plan (32B/Claude)
    4. Return plan and greeting
    """
    try:
        # Load strategy configuration
        config_path = Path.home() / ".language_tutor_config.json"
        if not config_path.exists():
            raise HTTPException(
                status_code=400,
                detail="No configuration found. Run setup wizard first."
            )

        config = load_config(config_path)
        from language_tutor.hardware_strategy import STRATEGIES
        strategy = STRATEGIES[config["strategy"]]

        # Create session
        session = TutorSession(
            language=request.language,
            strategy=strategy,
            base_dir=Path("data"),
            memory_backend=request.memory_backend,
        )

        # Start session (generates plan with 32B/Claude)
        plan_result = await session.start(duration_minutes=request.duration_minutes)

        # Store session
        with _sessions_lock:
            active_sessions[session.session_id] = session

        voice_enabled = bool(strategy.get("voice_stt", {}).get("enabled", False))
        return StartSessionResponse(
            session_id=session.session_id,
            language=request.language,
            plan=plan_result["plan"],
            greeting=plan_result["greeting"],
            memory_backend=session.memory_backend,
            voice_enabled=voice_enabled,
        )

    except Exception as e:
        import traceback
        traceback.print_exc()  # add this line
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/end", response_model=EndSessionResponse)
async def end_session(request: EndSessionRequest):
    """
    End a tutoring session.

    This triggers:
    1. Generate summary (32B/Claude)
    2. Store summary in memory
    3. Update statistics
    4. Cleanup session
    """
    try:
        session = active_sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # End session (generates summary with 32B/Claude)
        summary_result = await session.end_session()

        # Remove from active sessions
        with _sessions_lock:
            active_sessions.pop(request.session_id, None)

        return EndSessionResponse(
            session_id=request.session_id,
            summary=summary_result["summary"],
            statistics=summary_result["statistics"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """Get current session status."""
    try:
        session = active_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionStatusResponse(
            session_id=session_id,
            language=session.language,
            state=session.state.value,
            memory_backend=session.memory_backend,
            active=session.state.value not in ["completed", "error"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reference-stack", response_model=ReferenceStackResponse)
async def get_reference_stack(
    language: str = "spanish",
    memory_backend: str = "engram",
    strategy: str = "local_everything",
):
    """Describe how the reference app composes the current ai_tools stack.

    This endpoint exists primarily for teaching, documentation alignment, and
    future inspector/workbench integration. It does not require a live session
    or local model service.
    """
    normalized_backend = (memory_backend or "engram").strip().lower()
    if normalized_backend != "engram":
        raise HTTPException(
            status_code=400,
            detail="memory_backend must be 'engram'",
        )

    normalized_strategy = (strategy or "local_everything").strip()
    if normalized_strategy not in STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{normalized_strategy}'",
        )

    stack = build_reference_stack(
        language=language,
        memory_backend=normalized_backend,
        strategy=normalized_strategy,
    )
    return ReferenceStackResponse(**asdict(stack))


@router.get("/active")
async def list_active_sessions():
    """List all active sessions."""
    return {
        "sessions": [
            {
                "session_id": sid,
                "language": session.language,
                "state": session.state.value,
            }
            for sid, session in active_sessions.items()
        ]
    }


def _store_for_language(language: str) -> SessionStore:
    """Return a SessionStore for the given language.

    base_dir resolution order:
    1. base_dir from any active session for this language  — always correct
    2. data_dir from ~/.language_tutor_config.json
    3. Path("data") relative to cwd                       — fallback

    This ensures history and active sessions always share the same database.
    """
    # Prefer base_dir from a live session — guaranteed to match
    with _sessions_lock:
        for session in active_sessions.values():
            if session.language == language:
                base_dir = session.base_dir
                return SessionStore(
                    db_path=base_dir / "memory" / f"{language}_sessions.db"
                )

    # No active session — derive from config or cwd default
    config_path = Path.home() / ".language_tutor_config.json"
    config = load_config(config_path) or {}
    base_dir = Path(config.get("data_dir", "data"))
    return SessionStore(db_path=base_dir / "memory" / f"{language}_sessions.db")


@router.get("/history/{language}")
async def get_session_history(language: str, limit: int = Query(default=10, ge=1, le=100)):
    """Return recent completed sessions for a language."""
    try:
        store = _store_for_language(language)
        sessions = store.get_session_history(language, limit=limit)
        return {"language": language, "sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/{language}")
async def get_session_stats(language: str):
    """Return aggregate user stats for a language."""
    try:
        store = _store_for_language(language)
        stats = store.get_user_stats(language)
        return {"language": language, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/{session_id}")
async def get_memory_snapshot(session_id: str):
    """Return a full snapshot of Engram memory for the active session.

    Called by the memory viewer tab. Returns working turns, recent episodes,
    semantic vocabulary, mistake nodes, and raw layer stats.
    """
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        mem = session.memory

        # --- Working memory ---
        turns = []
        try:
            raw_turns = mem.get_recent_turns(n=50)
            for t in raw_turns:
                turns.append({
                    "role":    getattr(t, "role", "?"),
                    "content": getattr(t, "content", str(t))[:500],
                })
        except Exception:
            pass

        # --- Episodes ---
        episodes = []
        try:
            raw_eps = mem.search_episodes("session", n=10, min_importance=0.0)
            for ep in raw_eps:
                episodes.append({
                    "text":       getattr(ep, "text", str(ep))[:400],
                    "importance": getattr(ep, "importance", None),
                    "timestamp":  str(getattr(ep, "timestamp", "")),
                })
        except Exception:
            pass

        # --- Semantic vocabulary ---
        vocabulary = []
        mistakes   = []
        try:
            if mem.helpers is not None:
                for diff in ("beginner", "intermediate", "advanced"):
                    rows = mem.helpers.find_unmastered_words(
                        user_id="default", difficulty=diff
                    )
                    for r in rows:
                        vocabulary.append({
                            "word":        r.get("word", ""),
                            "translation": r.get("translation", ""),
                            "difficulty":  diff,
                        })
        except Exception:
            pass

        # Mistake nodes via Kuzu query
        try:
            if mem.semantic is not None:
                rows = mem.semantic.query(
                    """
                    MATCH (m:Mistake)
                    RETURN m.incorrect AS incorrect,
                           m.correct   AS correct,
                           m.error_type AS error_type,
                           m.frequency  AS frequency
                    ORDER BY m.frequency DESC
                    LIMIT 20
                    """
                )
                for r in rows:
                    mistakes.append(dict(r))
        except Exception:
            pass

        # --- Layer stats ---
        stats = {}
        try:
            stats = mem.get_stats()
        except Exception:
            pass

        # --- SessionStore vocab mastery ---
        mastery_stats = {}
        due_words = []
        try:
            mastery_stats = session.store.get_vocab_stats(session.language)
            due_words = session.store.get_vocab_due(session.language, limit=20)
        except Exception:
            pass

        return {
            "session_id":    session_id,
            "language":      session.language,
            "working_turns": turns,
            "episodes":      episodes,
            "vocabulary":    vocabulary,
            "mistakes":      mistakes,
            "layer_stats":   stats,
            "mastery_stats": mastery_stats,
            "due_words":     due_words,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
