# Language Tutor — Task Tracker

Authoritative task list. Update when tasks complete or new ones are identified.

## Status
Phases 1–3 complete. Phase 4 (XTTS) is future work.

## Legend
- ✅ Complete
- 🔄 In progress
- ⬜ Not started / future
- ❌ Blocked

---

## Phase 1 — Text-based tutoring (Complete)

### Core Architecture
- ✅ Hardware detection and strategy system (`hardware_strategy.py`)
- ✅ Engine manager — planner/executor lifecycle (`engine_manager.py`)
- ✅ TutorSession orchestrator with Engram integration (`tutor_session.py`)
- ✅ SessionStore — SQLite persistence for stats and weakness history
- ✅ FastAPI application with CORS, static files, exception handler
- ✅ Setup wizard and preflight check

### Memory (Engram Integration)
- ✅ ProjectMemory initialisation with LANGUAGE_TUTOR project type
- ✅ Working memory — conversation turns
- ✅ Episodic memory — past session summaries (bypass_filter=True)
- ✅ Semantic memory — VocabularyWord nodes via LanguageTutorHelpers
- ✅ Semantic memory — Mistake nodes + MADE_MISTAKE edges
- ✅ Neural memory — surprise filter (when LLM engine supports logprobs)
- ✅ `add_turn` / `build_prompt` / `store_episode` / `search_episodes` wired
- ✅ `index_text` for cold layer / graph edge extraction

### Session Flow
- ✅ Session planning with planner model (weakness-aware prompt)
- ✅ Conversation loop: add_turn → build_prompt → generate → extract corrections/vocab
- ✅ Session summary generation and episodic storage
- ✅ Session stats persisted to SessionStore on end_session
- ✅ Idle session reaper (2-hour TTL, daemon thread)
- ✅ sessionStorage-based session ID recovery on page refresh

### Drill System
- ✅ DrillSystem — Spanish: irregular verbs, reflexive, prepositions, dictation, listening
- ✅ DrillSystem — Latin: irregular verbs (present/imperfect/perfect), noun declensions, prepositions
- ✅ Language-aware drill type dispatch
- ✅ Weakness-based drill recommendation via Engram Mistake node query
- ✅ Day-of-week fallback schedule (language-specific)
- ✅ Accent-tolerant answer checking for Spanish
- ✅ Word-level accuracy scoring for dictation

### Content
- ✅ `content/spanish.py` — irregular verbs, reflexive, prepositions, practice sentences
- ✅ `content/latin.py` — irregular verbs, noun declensions, prepositions, Classical sentences
- ✅ Spanish system prompt + internal guidelines + conversation starters
- ✅ Latin system prompt + internal guidelines + conversation starters

### API Routes
- ✅ `POST /api/session/start` — plan + greeting
- ✅ `POST /api/session/end` — summary + stats
- ✅ `GET  /api/session/status/{session_id}`
- ✅ `GET  /api/session/history/{language}` — recent sessions from SessionStore
- ✅ `GET  /api/session/stats/{language}` — aggregate user stats
- ✅ `POST /api/conversation/message` — text conversation turn
- ✅ `POST /api/conversation/drill` — get drill question
- ✅ `POST /api/conversation/drill/check` — check answer
- ✅ `GET  /api/conversation/drill/types?language=` — language-specific type list
- ✅ `GET  /api/conversation/metrics/{session_id}`
- ✅ `GET  /api/conversation/history/{session_id}`

### Frontend
- ✅ Language selection view
- ✅ Pre-session view with planning spinner + rotating messages
- ✅ Active session view: header stats bar, plan panel, chat, feedback feed
- ✅ Corrections and vocabulary surfaced as dismissible cards
- ✅ Typing indicator during LLM generation
- ✅ Drill panel with type selector, question/result states, running accuracy
- ✅ Drill type list populated dynamically per language
- ✅ Session summary modal with stats grid
- ✅ End-session confirmation dialog
- ✅ Session history collapsible on pre-session screen
- ✅ Error toast notifications

### Testing
- ✅ Integration test harness (`tests/test_engram_integration.py`)
  - 9 tests covering init, 5 exchanges, exchange count, end_session,
    store weaknesses, working memory stats, episodic stats, helpers, report
  - Auto-detects best available Ollama model

---

## Phase 2 — Voice pipeline (Mostly complete)

- ✅ `STTService` — faster-whisper, async, thread-pool executor
- ✅ `PiperTTSService` — piper CLI subprocess, base64 WAV output
- ✅ `VoicePipeline` — unified wrapper with Latin phonetic pre-processing hook
- ✅ `POST /api/conversation/audio` — multipart upload, STT → LLM → TTS
- ✅ Mic button (🎙️) in frontend — MediaRecorder, hold-to-record
- ✅ Base64 WAV playback in browser after audio response
- ✅ Mic button shown/hidden based on `strategy.voice_stt.enabled`
- ⬜ Latin phonetic G2P pipeline (CLTK) — placeholder in `voice/tts.py _latin_phonetic()`
- ✅ Pronunciation scoring (`drills/pronunciation.py`) — Whisper word timestamps + MFCC + fluency
- ✅ Pronunciation drill type wired into DrillSystem + `/audio/pronunciation` endpoint + record UI

---

## Phase 3 — Drill expansion

- ✅ Pronunciation drill — PronunciationScorer, /audio/pronunciation endpoint, record UI in drill panel
- ✅ Vocabulary spaced-repetition drill — SM-2 (5 mastery levels, seed from vocab_log)
- ✅ Translation drill — LLM-graded, falls back to fuzzy match without engine
- ✅ Grammar explanation — POST /api/conversation/explain, "Explain" button on correction cards
- ✅ Listening comprehension with TTS audio — /drill route generates base64 WAV, frontend plays it

---

---

> **Phase 1–3 complete.** All text, drill, voice pipeline, and memory
> integration features are implemented. Remaining work is Phase 4
> (XTTS voice cloning) and infrastructure (session persistence, containers).

## Phase 4 — XTTS Latin voice cloning

- ⬜ `XTTSService` — CoquiTTS XTTS v2 inference
- ⬜ Voice cloning from family recordings (wife_clone sample)
- ⬜ Qwen3-TTS fine-tuning on Classical Latin phonetics
  - Key question: does fine-tuning on male Latin speakers preserve female voice cloning?
- ⬜ Wire XTTS into `VoicePipeline._get_tts()` for `tts_backend == "xtts"`
- ⬜ Update LATIN_PROFILE: `tts_backend="xtts"`, `tts_voice="wife_clone"`

---

## Infrastructure / Hygiene

- ✅ `voice/tts.py` — real VoicePipeline (was stub)
- ✅ `drills/base.py` — ImportError guard (design stub)
- ✅ `drills/pronunciation.py` — ImportError guard (design stub)
- ✅ CORS: configurable via CORS_ORIGINS env var, defaults to localhost:8080
- ✅ Preflight check: piper binary + voice model + faster-whisper checks added
- ✅ Whisper Latin quality: WHISPER_LANGUAGE=auto env var for auto-detection; noted in preflight
- ⬜ Session persistence: in-memory with 2hr reaper is sufficient for local single-user use;
  Redis/SQLite migration only needed for multi-worker deployment

---

## LLM Course integration (future)

- ⬜ Language Tutor as Module 6 case study in LLM applications course
- ⬜ Sandboxed demo environment (containers, no GPU required)
- ⬜ Student-facing documentation

---

*Last updated: 2026-03*
