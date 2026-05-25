# language_tutor slice

A minimal, runnable example: **one memory-augmented Spanish tutoring turn**,
built against only the public APIs of `engram` and `llm_engines`.

This is the API acceptance test for the stable packages (MEMBERSHIP step 4).
If the turn loop can be built and run using only the public surfaces, the API
is sufficient for real apps. See `API_ACCEPTANCE_FINDINGS.md` for the verdict.

## What it does

Per turn: records the user message in memory, asks `engram` to assemble a
memory-augmented prompt (retrieval + token budgeting), sends that prompt to an
`llm_engines` engine, records the reply, and indexes the exchange for future
retrieval.

The engine is injected through the public `ChatModel` protocol, so the same
turn logic runs against a real Ollama model or an offline stub.

## Files

- `tutor_turn.py` — the turn loop (`run_turn`). Public symbols only. The core.
- `vocab.py` — a small harvested Spanish vocab set + tutor system prompt.
- `stub_engine.py` — offline `ChatModel` stub for testing without a model.
- `run_slice.py` — runnable entry point (real Ollama or `--stub`).
- `test_slice.py` — offline test; the executable acceptance test.
- `API_ACCEPTANCE_FINDINGS.md` — what the build surfaced.

## Run

Offline (no model needed):

    python -m language_tutor_slice.run_slice --stub
    pytest examples/language_tutor_slice/test_slice.py

Real model (Ollama running locally):

    python -m language_tutor_slice.run_slice --model qwen3:8b

## Scope

Deliberately one vertical slice. Drills/SM-2, voice, and the planner/executor
split are out of scope here — they are later slices once this basic
memory+engine wiring is proven through the public API.
