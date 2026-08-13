"""
Conversation Routes

Endpoints for sending messages and receiving responses.
"""

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import TYPE_CHECKING, Dict, Optional, List

if TYPE_CHECKING:
    from language_tutor.drills.pronunciation import PronunciationScorer
    from language_tutor.voice.piper_tts import PiperTTSService
    from language_tutor.voice.stt import STTService

from language_tutor.routes.session import active_sessions

router = APIRouter()


class MessageRequest(BaseModel):
    """Request to send a message."""
    session_id: str
    message: str


class MessageResponse(BaseModel):
    """Response from tutor."""
    session_id: str
    message: str
    corrections: Optional[List[dict]] = None
    new_vocabulary: Optional[List[dict]] = None
    metadata: Optional[dict] = None


@router.post("/message", response_model=MessageResponse)
async def send_message(request: MessageRequest):
    """
    Send a message to the tutor and get a response.

    This triggers:
    1. Add user message to working memory
    2. Retrieve context (working + episodic + semantic)
    3. Generate response (7B/Claude)
    4. Store episode (surprise-gated if local)
    5. Extract corrections and new vocabulary
    """
    try:
        # Get session
        session = active_sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Handle message
        response = await session.handle_text(request.message)

        return MessageResponse(
            session_id=request.session_id,
            message=response.text,
            corrections=response.corrections,
            new_vocabulary=response.new_vocabulary,
            metadata=response.metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/{session_id}")
async def websocket_conversation(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time conversation.

    This is optional for Phase 1 but nice to have for streaming responses.
    """
    await websocket.accept()

    try:
        # Get session
        session = active_sessions.get(session_id)
        if not session:
            await websocket.send_json({
                "error": "Session not found",
                "session_id": session_id,
            })
            await websocket.close()
            return

        while True:
            # Receive message
            data = await websocket.receive_json()
            user_message = data.get("message")

            if not user_message:
                continue

            # Handle message
            response = await session.handle_text(user_message)

            # Send response
            await websocket.send_json({
                "message": response.text,
                "corrections": response.corrections,
                "new_vocabulary": response.new_vocabulary,
                "metadata": response.metadata,
            })

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for session {session_id}")

    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()


@router.get("/history/{session_id}")
async def get_conversation_history(session_id: str, limit: int = 50):
    """
    Get conversation history for a session.

    Returns recent message exchanges from working memory.
    """
    try:
        session = active_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        turns = session.memory.get_recent_turns(n=limit)

        return {
            "session_id": session_id,
            "history": [
                {
                    "role": getattr(turn, "role", "unknown"),
                    "content": getattr(turn, "content", str(turn)),
                    "timestamp": getattr(turn, "timestamp", None),
                }
                for turn in turns
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{session_id}")
async def get_session_metrics(session_id: str):
    """Get evaluation metrics for an active session."""
    try:
        session = active_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session.get_eval_metrics()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Grammar explanation
# ---------------------------------------------------------------------------

class ExplainRequest(BaseModel):
    """Request a grammar explanation from the planner model."""
    session_id: str
    text: str                        # The phrase, error, or concept to explain
    question: Optional[str] = None   # Optional: "Why is X wrong?" "What does Y mean?"


@router.post("/explain")
async def explain_grammar(request: ExplainRequest):
    """Use the planner (larger) model to give a deep grammar explanation."""
    try:
        session = active_sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        explanation = await session.explain(request.text, request.question)
        return {"explanation": explanation, "text": request.text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LookupRequest(BaseModel):
    session_id: str
    word: str                        # selected word or phrase
    context: Optional[str] = None    # surrounding sentence for disambiguation


@router.post("/lookup")
async def lookup_word(request: LookupRequest):
    """Contextual word/phrase lookup using the executor model.

    Returns translation, part of speech, usage notes, and example.
    Automatically logs the word to vocab_log for SM-2 tracking.
    """
    try:
        session = active_sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        lang = session.profile.name
        prompt = (
            f"A student is learning {lang} and selected this word or phrase:\n\n"
            f"Word/phrase: {request.word}\n"
            + (f"Context sentence: {request.context}\n" if request.context else "")
            + f"\nProvide a concise lookup entry. Respond with JSON only:\n"
            f'{{"translation": "primary English meaning", '
            f'"alternatives": ["other meaning 1", "other meaning 2"], '
            f'"part_of_speech": "noun/verb/etc", '
            f'"notes": "usage note or disambiguation if relevant", '
            f'"example": "short example sentence in {lang}"}}'
        )

        raw = session.executor.generate(
            prompt=prompt,
            system_prompt=f"You are a {lang} dictionary. Respond only with JSON.",
            max_tokens=200,
        )

        # Parse JSON response
        import json as _json
        import re as _re
        result = {}
        try:
            raw_clean = _re.sub(r'^```[a-z]*\s*|\s*```$', '', raw.strip(), flags=_re.MULTILINE)
            result = _json.loads(raw_clean)
        except Exception:
            m = _re.search(r'\{.*\}', raw, _re.DOTALL)
            if m:
                try:
                    result = _json.loads(m.group())
                except Exception:
                    pass

        if not result:
            result = {"translation": raw.strip()[:200], "alternatives": [], "notes": ""}

        # Log to vocab for SM-2 tracking
        try:
            translation = result.get("translation", "")
            if translation:
                session.store.log_vocab(
                    session.session_id, session.language,
                    request.word, translation,
                )
        except Exception:
            pass

        return {"word": request.word, **result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CheckRequest(BaseModel):
    session_id: str
    text: str    # user input to check before submitting


@router.post("/check")
async def check_input(request: CheckRequest):
    """Pre-submission grammar and spelling check.

    Returns a list of errors with positions, type, and suggestion.
    Uses the executor model for language-aware checking (accents, conjugation,
    gender agreement) not just spell-checking.
    """
    try:
        session = active_sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        lang = session.profile.name
        prompt = (
            f"Check this {lang} text for errors. Find: misspellings, wrong accents "
            f"(e.g. 'esta' vs 'está'), wrong verb conjugation, gender agreement errors.\n\n"
            f"Text: {request.text}\n\n"
            f"Return JSON array only (empty array if no errors):\n"
            f'[{{"start": 0, "end": 4, "error": "incorrect text", '
            f'"suggestion": "corrected text", "type": "accent|spelling|conjugation|agreement", '
            f'"hint": "brief explanation"}}]'
        )

        raw = session.executor.generate(
            prompt=prompt,
            system_prompt=f"You are a {lang} grammar checker. Respond only with a JSON array.",
            max_tokens=400,
        )

        import json as _json
        import re as _re
        errors = []
        try:
            raw_clean = _re.sub(r'^```[a-z]*\s*|\s*```$', '', raw.strip(), flags=_re.MULTILINE)
            parsed = _json.loads(raw_clean)
            if isinstance(parsed, list):
                errors = parsed
        except Exception:
            m = _re.search(r'\[.*\]', raw, _re.DOTALL)
            if m:
                try:
                    errors = _json.loads(m.group())
                except Exception:
                    pass

        return {"text": request.text, "errors": errors}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Drill endpoints
# ---------------------------------------------------------------------------

class DrillRequest(BaseModel):
    """Request a drill question."""
    session_id: str
    drill_type: Optional[str] = "auto"  # auto, mixed_review, irregular_verbs_preterite, etc.


class DrillCheckRequest(BaseModel):
    """Submit an answer to the active drill question."""
    session_id: str
    user_answer: str


@router.post("/drill")
async def get_drill_question(request: DrillRequest):
    """Get the next drill question for the session.

    For sentence_dictation and listening_comprehension drills, the response
    includes `audio_b64`: a base64-encoded WAV of the target sentence spoken
    via piper TTS (when a model is available). The frontend plays this audio
    and hides the text so the student must listen, not read.
    """
    try:
        session = active_sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        question = session.get_drill(request.drill_type)

        # Generate TTS audio for listening drills
        audio_b64: Optional[str] = None
        if question.get("auto_play_tts"):
            tts = _get_tts()
            if tts is not None:
                try:
                    sentence = question.get("correct_answer", "")
                    if sentence:
                        audio_b64 = await tts.generate_speech(sentence, speed="slow")
                except Exception:
                    pass  # TTS failure is non-fatal; drill continues without audio

        return {**question, "audio_b64": audio_b64}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drill/check")
async def check_drill_answer(request: DrillCheckRequest):
    """
    Check the user's answer against the active drill question.

    Must be called after /drill — the question is cached on the session.
    Returns correct/incorrect, feedback, and updated drill stats.
    """
    try:
        session = active_sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        result = session.check_drill(request.user_answer)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drill/types")
async def list_drill_types(language: str = Query(default="spanish")):
    """List drill types available for the given language."""
    if language in ("latin", "la"):
        types = [
            {"id": "auto",                        "label": "Auto (recommended)"},
            {"id": "mixed_review",                "label": "Mixed Review"},
            {"id": "vocabulary_review",           "label": "Vocabulary Review (spaced repetition)"},
            {"id": "translation",                  "label": "Translation (LLM graded)"},
            {"id": "pronunciation",               "label": "Pronunciation (voice)"},
            {"id": "irregular_verbs_present",     "label": "Irregular Verbs — Present"},
            {"id": "irregular_verbs_imperfect",   "label": "Irregular Verbs — Imperfect"},
            {"id": "irregular_verbs_perfect",     "label": "Irregular Verbs — Perfect"},
            {"id": "noun_declensions",            "label": "Noun Declensions"},
            {"id": "prepositions",                "label": "Prepositions + Case"},
            {"id": "sentence_dictation",          "label": "Sentence Dictation"},
            {"id": "listening_comprehension",     "label": "Listening Comprehension"},
        ]
    else:
        types = [
            {"id": "auto",                        "label": "Auto (recommended)"},
            {"id": "mixed_review",                "label": "Mixed Review"},
            {"id": "vocabulary_review",           "label": "Vocabulary Review (spaced repetition)"},
            {"id": "translation",                  "label": "Translation (LLM graded)"},
            {"id": "pronunciation",               "label": "Pronunciation (voice)"},
            {"id": "irregular_verbs_preterite",   "label": "Irregular Verbs — Preterite"},
            {"id": "irregular_verbs_imperfect",   "label": "Irregular Verbs — Imperfect"},
            {"id": "reflexive_verbs",             "label": "Reflexive Verbs"},
            {"id": "prepositions",                "label": "Verb + Preposition"},
            {"id": "sentence_dictation",          "label": "Sentence Dictation"},
            {"id": "listening_comprehension",     "label": "Listening Comprehension"},
        ]
    return {"language": language, "types": types}


# ---------------------------------------------------------------------------
# Voice / Audio route
# ---------------------------------------------------------------------------

# Module-level singletons keyed by language — created lazily on first request.
_stt_services: Dict[str, "STTService"] = {}
_tts_service: Optional["PiperTTSService"] = None
_tts_unavailable: bool = False   # Set True once we've confirmed piper model is missing


def _get_stt(language: str) -> "STTService":
    """Return (or create) the STTService for *language*."""
    from language_tutor.voice.stt import STTService
    from language_tutor.config import get_language_profile
    if language not in _stt_services:
        profile = get_language_profile(language)
        _stt_services[language] = STTService(
            language=profile.whisper_language or "es",
        )
    return _stt_services[language]


def _get_tts() -> Optional["PiperTTSService"]:
    """Return the PiperTTSService, or None if no model is available."""
    global _tts_service, _tts_unavailable
    if _tts_unavailable:
        return None
    if _tts_service is None:
        try:
            from language_tutor.voice.piper_tts import PiperTTSService
            _tts_service = PiperTTSService()
        except RuntimeError:
            # No piper model installed — TTS simply won't work
            _tts_unavailable = True
            return None
    return _tts_service


class AudioMessageResponse(BaseModel):
    """Response from the audio endpoint — same fields as MessageResponse plus optional TTS audio."""
    session_id: str
    message: str
    transcription: str
    corrections: Optional[List[dict]] = None
    new_vocabulary: Optional[List[dict]] = None
    audio_response: Optional[str] = None   # base64 WAV from piper, or None
    metadata: Optional[dict] = None


@router.post("/audio", response_model=AudioMessageResponse)
async def send_audio(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """
    Accept a voice recording and return a text + optional audio response.

    Steps:
      1. Read audio bytes from the upload
      2. Transcribe with faster-whisper (STTService)
      3. Pass transcription to session.handle_text()
      4. Synthesise the response with piper (PiperTTSService), if model is available
      5. Return transcription, text response, corrections/vocab, base64 WAV

    Accepts any audio format faster-whisper supports (WAV, WebM, OGG, MP4, etc.).
    """
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        audio_bytes = await audio.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read audio: {e}")

    # STT
    try:
        stt = _get_stt(session.language)
        transcription = await stt.transcribe_bytes(audio_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    if not transcription or transcription.startswith("[transcription error"):
        raise HTTPException(
            status_code=422,
            detail=f"No speech detected or transcription error: {transcription}",
        )

    # LLM response
    try:
        response = await session.handle_text(transcription)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # TTS (best-effort — skip silently if piper not configured)
    audio_response: Optional[str] = None
    tts = _get_tts()
    if tts is not None:
        try:
            audio_response = await tts.generate_speech(response.text, speed="normal")
        except Exception:
            pass   # TTS failure should not break the conversation

    return AudioMessageResponse(
        session_id=session_id,
        message=response.text,
        transcription=transcription,
        corrections=response.corrections,
        new_vocabulary=response.new_vocabulary,
        audio_response=audio_response,
        metadata=response.metadata,
    )


# Module-level scorer cache keyed by language
_pronunciation_scorers: Dict[str, "PronunciationScorer"] = {}

def _get_scorer(language: str) -> "PronunciationScorer":
    from language_tutor.drills.pronunciation import PronunciationScorer
    from language_tutor.config import get_language_profile
    if language not in _pronunciation_scorers:
        profile = get_language_profile(language)
        _pronunciation_scorers[language] = PronunciationScorer(
            language=profile.whisper_language or language,
        )
    return _pronunciation_scorers[language]


@router.post("/audio/pronunciation")
async def score_pronunciation(
    session_id: str = Form(...),
    expected_text: str = Form(...),
    audio: UploadFile = File(...),
):
    """Score a pronunciation drill attempt.

    The client POSTs:
      - session_id: active session
      - expected_text: the sentence the student should have said
      - audio: the recorded audio file (WAV/WebM/OGG)

    Returns pronunciation score dict:
      score, phonetic_accuracy, fluency_score, feedback,
      detected_text (what Whisper heard), expected_text.
    """
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        audio_bytes = await audio.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read audio: {e}")

    try:
        scorer = _get_scorer(session.language)
        result = await scorer.score(audio_bytes, expected_text)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Pronunciation scoring requires faster-whisper: "
                   "pip install faster-whisper --break-system-packages",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Log poor pronunciation as a mistake for future drill weighting
    if result["score"] < 60 and session is not None:
        try:
            session.store.log_mistake(
                session.session_id, session.language,
                result["detected_text"], expected_text,
                error_type="pronunciation",
            )
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Duolingo vocabulary import
# ---------------------------------------------------------------------------

class ImportRequest(BaseModel):
    session_id: str
    text: str        # raw pasted text from Duolingo


@router.post("/import/vocabulary")
async def import_vocabulary(request: ImportRequest):
    """Parse and import Duolingo vocabulary paste.

    Expects alternating lines: Spanish word, English translation, blank line.
    Deduplicates, enriches with LLM (batch of 5), merges into vocabulary_mastery.
    Never resets mastery level on duplicates.
    """
    try:
        session = active_sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        import json as _json
        import re as _re

        # --- Parse the paste ---
        # Split on blank lines to get pairs; handle both \r\n and \n
        raw_pairs = []
        blocks = _re.split(r'\n\s*\n', request.text.strip())
        for block in blocks:
            lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
            if len(lines) >= 2:
                raw_pairs.append((lines[0], lines[1]))
            elif len(lines) == 1:
                # Single line — store word with empty translation for enrichment
                raw_pairs.append((lines[0], ""))

        if not raw_pairs:
            return {"imported": 0, "skipped": 0, "words": [], "error": "No word pairs found in paste."}

        # Deduplicate within the paste itself
        seen = set()
        pairs = []
        for word, trans in raw_pairs:
            key = word.lower().strip()
            if key not in seen:
                seen.add(key)
                pairs.append((word, trans))

        lang = session.language

        # --- Enrich in batches of 5 ---
        async def enrich_batch(batch):
            words_json = _json.dumps([{"word": w, "duolingo_translation": t} for w, t in batch])
            prompt = (
                f"Enrich these {session.profile.name} vocabulary words. "
                f"For each word provide full translations (all common meanings), "
                f"part of speech, and a short example sentence.\n\n"
                f"Input: {words_json}\n\n"
                f"Respond with a JSON array in the same order:\n"
                f'[{{"word": "...", "translation": "primary meaning", '
                f'"alternatives": ["meaning2", "meaning3"], '
                f'"part_of_speech": "...", "example": "..."}}]'
            )
            raw = session.executor.generate(
                prompt=prompt,
                system_prompt=f"You are a {session.profile.name} dictionary. Respond only with JSON.",
                max_tokens=600,
            )
            try:
                clean = _re.sub(r'^```[a-z]*\s*|\s*```$', '', raw.strip(), flags=_re.MULTILINE)
                return _json.loads(clean)
            except Exception:
                m = _re.search(r'\[.*\]', raw, _re.DOTALL)
                if m:
                    try:
                        return _json.loads(m.group())
                    except Exception:
                        pass
            # Fallback: return bare pairs without enrichment
            return [{"word": w, "translation": t, "alternatives": []} for w, t in batch]

        enriched = []
        batch_size = 5
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i + batch_size]
            results = await enrich_batch(batch)
            # Align results with input batch (LLM may return fewer)
            for j, (word, orig_trans) in enumerate(batch):
                if j < len(results):
                    entry = results[j]
                else:
                    entry = {"word": word, "translation": orig_trans, "alternatives": []}
                enriched.append(entry)

        # --- Merge into vocabulary_mastery (never reset mastery) ---
        imported = 0
        skipped  = 0
        for entry in enriched:
            word        = entry.get("word", "").strip()
            translation = entry.get("translation", "").strip()
            alts        = entry.get("alternatives", [])
            if alts:
                full_translation = translation + "; " + "; ".join(alts)
            else:
                full_translation = translation

            if not word:
                continue

            try:
                # Check if already exists
                existing = session.store.get_vocab_due(lang, limit=1000)
                existing_words = {e["word"].lower() for e in existing}

                if word.lower() in existing_words:
                    # Update translation only if richer; never touch mastery
                    with session.store._conn() as conn:
                        row = conn.execute(
                            "SELECT translation FROM vocabulary_mastery WHERE language=? AND word=?",
                            (lang, word),
                        ).fetchone()
                        if row and len(full_translation) > len(row["translation"] or ""):
                            conn.execute(
                                "UPDATE vocabulary_mastery SET translation=? WHERE language=? AND word=?",
                                (full_translation[:300], lang, word),
                            )
                    skipped += 1
                else:
                    session.store.record_vocab_result(lang, word, full_translation[:300], correct=False)
                    session.store.log_vocab(session.session_id, lang, word, full_translation[:300])
                    imported += 1
            except Exception:
                skipped += 1

        return {
            "imported": imported,
            "skipped":  skipped,
            "words":    [{"word": e.get("word",""), "translation": e.get("translation","")} for e in enriched],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
