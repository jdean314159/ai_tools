# Language Tutor

`language_tutor` is the main reference application in the `ai_tools` monorepo.

It is not just a standalone tutor. It exists to demonstrate how the stack is supposed to be composed in a real application:

- `llm_engines` for model/backend abstraction
- `engram` for memory through a tutor-owned protocol
- drill and session logic as application behavior
- `llm_inspector` / `llm_inspector_ui` as the long-term observability path

That makes `language_tutor` both:

1. a usable application, and
2. a concrete integration vehicle for validating the library stack

---

## Start here if you are learning from this repo

If you are using `language_tutor` as part of the teaching path, read these in order:

1. [`../LEARNING_PATH.md`](../LEARNING_PATH.md) — where this package sits in the full curriculum
2. [`REFERENCE_APP_GUIDE.md`](./REFERENCE_APP_GUIDE.md) — guided walkthrough of the app as a composed system
3. this `README.md` — package-specific details, API surface, and setup notes

---

## Current role in the repo

`language_tutor` should be treated as the canonical reference app for the suite, not an unrelated side project.

Its job is to answer practical questions such as:

- what does a real application built on this stack look like?
- how should `llm_engines`, memory, and application logic fit together?
- what integration problems appear in practice?
- how do memory choices affect behavior in a real user workflow?

The package therefore matters even when the immediate work is on shared libraries.

---

## Architectural position

The intended composition path is:

```text
llm_engines + engram + language_tutor
```

with the longer-term observability path:

```text
language_tutor -> llm_inspector -> llm_inspector_ui
```

and, potentially in later phases:

```text
rag_lib -> language_tutor
```

for curriculum retrieval, explanation retrieval, or source-grounded tutoring content.

---

## Memory backends

| Backend | Default | Purpose |
|---------|---------|---------|
| `engram` | ✓ | Current project-memory path, isolated behind `TutorMemoryBackend`. |

You can select the backend when constructing `TutorSession(...)` or through the session start API.

The protocol remains useful even with one supported backend: it prevents
application code from depending on Engram internals and leaves a testable seam
for future implementations.

---

## High-level architecture

```text
language_tutor/
├── app.py                 FastAPI web server
├── config.py              language profiles and defaults
├── hardware_strategy.py   environment / hardware-driven execution choices
├── engine_manager.py      model lifecycle and engine selection
├── tutor_session.py       session orchestration (memory + drills + tutoring flow)
├── session_store.py       SQLite persistence for stats and review history
├── content/               language-learning content
├── drills/                drill types and scoring logic
├── voice/                 STT/TTS integration
├── routes/                HTTP API surface
└── templates/             single-page web UI
```

Conceptually, the package combines:

- application logic
- a realistic memory integration surface
- real engine integration
- optional voice paths
- a place to observe integration drift or architectural mismatch

---

## Teaching note

`language_tutor` should now be read as the canonical **composed application** in the suite:

- earlier stages teach engines, inspection, memory, and retrieval in isolation
- this package shows how those layers meet application state, user workflows, and HTTP/UI boundaries
- it is intentionally more concrete than the libraries and should be the first place a learner studies a full stack composition

To support teaching and future workbench integration, the app also exposes a machine-readable self-description endpoint:

```text
GET /api/session/reference-stack
```

That endpoint describes the current engine layer, memory layer, observability contracts, and forward integration path without requiring a live tutoring session.

---

## Quick start

```bash
# Run preflight check
./start.sh --preflight

# Start the web server
./start.sh
```

Or for a command-line session:

```bash
./start.sh --cli
```

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama server URL |
| `ANTHROPIC_API_KEY` | — | Required for cloud strategies |
| `PIPER_MODEL_PATH` | auto-detect | Path to `.onnx` voice model |
| `WHISPER_LANGUAGE` | profile default | Override STT language (`""` = auto-detect) |
| `CORS_ORIGINS` | `http://localhost:8080` | Comma-separated allowed origins |
| `LANGUAGE_TUTOR_STRATEGY` | auto-detect | Override hardware strategy |
| `LANGUAGE_TUTOR_DEBUG_EXCEPTIONS` | `0` | Return traceback details in HTTP responses only when explicitly enabled |
| `LANGUAGE_TUTOR_ALLOW_LEGACY_ENGINE_FALLBACK` | `1` | Allow fallback from modern `llm_engines` wiring to legacy engine path |

---

## What it demonstrates well now

- real `llm_engines`-backed application composition
- configurable lightweight versus full memory backends
- persistence across tutoring sessions
- deterministic integration tests with fake engines
- a realistic app surface that exposes where library contracts help or hurt

---

## What is still in transition

`language_tutor` still reflects some older stages of the repo and should be understood as a **migrating reference app**.

In particular:

- it is not yet fully aligned with the newer `llm_harness_core` interop layer
- its observability path is not yet as mature as the work already done for memory and RAG in the workbench
- it still contains traces of earlier standalone-app assumptions
- a future phase may integrate `rag_lib` for retrieval-backed tutoring content or explanations

So the current status is:

> valuable and important, but not yet the final form of the reference app architecture

---

## API surface

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/session/start` | Start session |
| POST | `/api/session/end` | End session + generate summary |
| GET | `/api/session/status/{id}` | Session state |
| GET | `/api/session/history/{lang}` | Past sessions |
| GET | `/api/session/stats/{lang}` | Aggregate stats |
| POST | `/api/conversation/message` | Text conversation turn |
| POST | `/api/conversation/explain` | Grammar explanation |
| POST | `/api/conversation/drill` | Get drill question |
| POST | `/api/conversation/drill/check` | Check drill answer |
| GET | `/api/conversation/drill/types` | Available drill types |
| POST | `/api/conversation/audio` | Voice input to text plus TTS response |
| POST | `/api/conversation/audio/pronunciation` | Score pronunciation attempt |
| GET | `/api/conversation/metrics/{id}` | Session evaluation metrics |

---

## Tests

`language_tutor` is explicitly meant to act as an integration vehicle for the other libraries in this repo.

Its supported memory backend is `engram`.

```bash
python -m pytest -q examples/language_tutor_reference_app/tests
```

The default tests are intended to cover:

- import safety without optional cloud SDKs installed
- strategy catalogue wiring across memory and engine layers
- `TutorSession` round-trips with persistent state
- the `USE_LLM_ENGINES=1` adapter path
- regression coverage for newer release-hardening behavior

Optional live Ollama smoke test:

```bash
LANGUAGE_TUTOR_LIVE_OLLAMA=1 python -m pytest -q \
  examples/language_tutor_reference_app/tests -k live_ollama
```

---

## Voice setup

**STT**

```bash
pip install faster-whisper --break-system-packages
```

**TTS**

```bash
# Download piper and a voice model, then set:
export PIPER_MODEL_PATH=/path/to/model.onnx
```

Voice support is optional and should be treated as an application extension path, not a prerequisite for understanding the core stack integration.

---

## Data layout

```text
data/
├── memory/
│   ├── spanish_tutor/
│   ├── latin_tutor/
│   ├── spanish_sessions.db
│   └── latin_sessions.db
└── voices/
```

---

## Reference-app walkthrough

A guided architectural walkthrough now lives at [`REFERENCE_APP_GUIDE.md`](./REFERENCE_APP_GUIDE.md).
Use it when the goal is to understand how `language_tutor` maps to the rest of the suite, not just to run the package.

---

## Forward direction

The most important future work for `language_tutor` is:

- align it more directly with `llm_harness_core`
- strengthen its observability path into `llm_inspector` / `llm_inspector_ui`
- decide whether and how `rag_lib` should support explanations or curriculum retrieval
- keep it current as the canonical example of how the suite is meant to be composed

---

## Project context

For repo-wide architecture and continuity, see:

- `../VISION.md`
- `../CURRENT_STATE.md`
- `../ROADMAP.md`
- `../ADR_INDEX.md`
