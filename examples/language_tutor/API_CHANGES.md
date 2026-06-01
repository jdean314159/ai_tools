# Language Tutor — API Changes & Refinement Record

Records public API changes and refinements made while building the
`examples/language_tutor` consumer.

## Required public API change: `GenerationResponse.text`

The example reads model text via `response.text`. `GenerationResponse` did not
originally expose `.text` (text lived at `response.message.content`). A `.text`
convenience property was added to `GenerationResponse` (additive, non-breaking).

Note: the initial Codex-generated draft assumed `.text` existed and would have
failed at runtime without this property. The acceptance-test slice independently
found the same gap and added the property — two independent builds converged on
the same single missing accessor, which is good evidence it belongs in the API.

This is the only public API change the language tutor required. Everything else
is built from existing public surfaces:

- `engram.ProjectMemory`
- `llm_engines`: `ChatModel`, `ChatMessage`, `GenerationRequest`,
  `GenerationResponse`, `get_engine`, `StructuredOutputHandler`
- `llm_harness_core`: `CapabilityDescriptor`, `CapabilityKind`, `MemoryRecord`,
  `OperationResult`, `TraceEvent`

## Refinements applied during adoption

1. **Structured output via the public handler.** Hand-rolled `_json_object` /
   `_json_list` regex parsing was replaced with
   `StructuredOutputHandler.parse_with_details` against Pydantic schemas
   (`LessonPlan`, `TurnAnalysis`, `WordLookup`, `TextCheck`). Prompts are
   generated from the schemas via `create_schema_prompt`. No new API was needed
   — `StructuredOutputHandler` is already public.

2. **Per-turn extraction cost reduced.** The original design (and the Codex
   draft) made three engine calls per conversational turn: reply +
   extract-corrections + extract-vocabulary. The two extraction calls were
   merged into a single `TurnAnalysis` call (3 → 2), and gated behind an
   `analyze` flag (`analyze=False` → 1 call) for low-latency local inference.
   The main reply remains a natural-language call so conversational quality is
   not sacrificed for structure.

## Verification status

Import-level acceptance check passes (all `ai_tools` imports resolve to public
`__all__` names). Runtime tests must be run locally — the build sandbox lacks
`pydantic` and network access. To close the loop:

    pytest examples/language_tutor/test_language_tutor.py
    python -m examples.language_tutor.run_demo --backend stub
    python -m examples.language_tutor.run_demo --backend ollama --model qwen3:8b
