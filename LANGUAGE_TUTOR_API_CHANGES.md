# Language Tutor API Changes

This file records public API changes needed while rebuilding the language tutor
capability as an `examples/` consumer.

## Current pass

No new `ai_tools` public API changes were required for
`examples/language_tutor`.

The example is intentionally built from existing public surfaces:

- `engram.ProjectMemory`
- `llm_engines.ChatModel`
- `llm_engines.ChatMessage`
- `llm_engines.GenerationRequest`
- `llm_engines.get_engine`
- `llm_harness_core.CapabilityDescriptor`
- `llm_harness_core.MemoryRecord`
- `llm_harness_core.OperationResult`
- `llm_harness_core.TraceEvent`

## Notes

The prior telemetry export change in `engram` was made to satisfy the existing
`engram` threshold telemetry test, not this language tutor rebuild.
