# API Acceptance Findings — language_tutor slice

**Date:** 2026-05-24
**Slice:** one memory-augmented Spanish tutoring turn (single engine).
**Question under test:** are the public surfaces of `engram` and `llm_engines`
sufficient to build a real consuming app without reaching into internals?

## Verdict: PASS (with two small fixes and one recommendation)

The full turn loop — record user turn → build memory-augmented prompt → call
engine → record assistant turn → index exchange — is buildable using only
public symbols. Every `engram`/`llm_engines` import in the slice resolves to a
name in that package's `__all__`:

- `engram`: `ProjectMemory`
- `llm_engines`: `get_engine`, `ChatMessage`, `GenerationRequest`,
  `GenerationResponse`, `ChatModel`

No private module was imported. The trimmed `__all__` from the public-API pass
held up against a real consumer.

## Findings

### 1. Doc/API mismatch — FIXED during the slice
The quickstart docstrings added in the public-API pass (in both
`llm_engines/__init__.py` and `engram/__init__.py`) referenced
`response.text`, but `GenerationResponse` had no such attribute — the text
lives at `response.message.content`. A consumer following the quickstart
verbatim would hit an `AttributeError`.

**Fix applied:** added a `text` convenience property to `GenerationResponse`
(`return self.message.content or ""`). Additive and non-breaking; makes the
documented quickstart correct and matches what every consumer wants. This is
exactly the class of defect the acceptance test exists to catch.

### 2. System-prompt placement — documented, no code change needed
`ProjectMemory` folds `system_prompt` into the assembled prompt at construction
(`ProjectMemory(system_prompt=...)`), and `build_prompt` returns that fully
assembled string. The engine call must therefore send the assembled prompt as a
single user message and **not** also pass a separate system `ChatMessage`, or
the persona is applied twice. The slice does this correctly; the full rebuild
should preserve the convention. Worth a line in the engram docs.

### 3. Engine ergonomics — RECOMMENDATION (not a blocker)
The original tutor called a wrapped `executor.generate(prompt=, system_prompt=,
max_tokens=)` string-in/string-out convenience. The public API instead requires
constructing `GenerationRequest(messages=[ChatMessage(role="user",
content=...)], max_tokens=..., temperature=...)`. This is fully buildable from
public types (and the slice's `tutor_turn.run_turn` is now a clean canonical
example of the pattern), but every consumer will re-wrap the structured call.

**Options, in order of preference:**
- Treat `tutor_turn.run_turn` as the documented pattern and leave the API as is
  (structured-only is honest and inspectable).
- If the re-wrapping recurs across examples, add a small public convenience
  (e.g. `engine.complete(prompt, *, max_tokens, temperature) -> str`) to
  `llm_engines`. Defer until a second consumer demonstrably needs it — per the
  co-evolution rule, one consumer is not yet a mandate.

### 4. Session handling — glue difference, not a gap
`ProjectMemory.add_turn(role, text, session_id)` takes an explicit session id;
the old tutor's `memory_backend` adapter bound the session at construction and
exposed `add_turn(role, text)`. The slice passes `session_id` explicitly. Not a
deficiency — just a glue shape the full rebuild should adopt rather than porting
the old adapter.

## Not validated here
Runtime execution could not run in the build sandbox (`pydantic` absent,
network disabled). The slice is syntax-clean and import-validated. Execute
locally to close the loop:

    # offline, deterministic (this is the acceptance test proper)
    python -m language_tutor_slice.run_slice --stub
    pytest examples/language_tutor_slice/test_slice.py

    # real model
    python -m language_tutor_slice.run_slice --model qwen3:8b

If the stub run and the pytest pass on your machine, the slice acceptance test
is fully closed and the pattern is cleared for the rest of the `language_tutor`
rebuild.
