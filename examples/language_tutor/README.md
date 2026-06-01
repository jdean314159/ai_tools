# Public-API Language Tutor Example

This example recreates the `language_tutor` reference app capability as a
consumer of public `ai_tools` APIs only.

It uses:

- `engram.ProjectMemory` for working/project memory and prompt assembly
- `llm_engines.ChatModel`, `GenerationRequest`, `ChatMessage`, and `get_engine`
  for model calls
- `llm_engines.StructuredOutputHandler` for typed JSON extraction (lesson plan,
  per-turn analysis, lookup, grammar check) — no hand-rolled JSON parsing
- `llm_harness_core` public contracts for capability, trace, memory, and result
  objects

It does not import from `language_tutor` or from package-private modules in
`engram`, `llm_engines`, or `llm_harness_core`.

## Cost and structured output

Structured fields are parsed with the public `StructuredOutputHandler` against
Pydantic schemas defined in `session.py`; the JSON instructions are generated
from those schemas via `create_schema_prompt`, and parsing is non-raising (a
malformed response degrades to empty rather than crashing a turn).

Per conversational turn the example makes **two** engine calls by default: one
natural-language reply, and one merged analysis call that extracts corrections
and new vocabulary together. Pass `analyze=False` to `LanguageTutor(...)` to
skip analysis entirely and run a **single**-call turn — useful for low-latency
local inference. The main reply is always a plain natural-language call so
conversational quality (and future streaming) is preserved.

## Capabilities

- session start with generated lesson plan
- memory-augmented conversation turns
- correction and vocabulary extraction
- grammar explanation
- contextual lookup
- pre-submit grammar check
- drill generation and checking
- vocabulary import and spaced-repetition tracking
- session summary, history, stats, metrics, and memory snapshot
- voice-shaped transcript handling and pronunciation scoring without requiring
  local STT/TTS dependencies
- interop output through shared `llm_harness_core` objects

## Run

Offline deterministic run:

```bash
python -m examples.language_tutor.run_demo --backend stub
```

Real engine run:

```bash
python -m examples.language_tutor.run_demo --backend ollama --model qwen3:8b
```

Graphical interface:

```bash
python -m examples.language_tutor.web_app
```

Then open `http://127.0.0.1:8090`. The UI defaults to Ollama with
`qwen3:8b`; switch the backend to `Offline stub` for a deterministic no-model
demo.

## Test

```bash
python -m pytest -q examples/language_tutor/test_language_tutor.py
```
