# Language Tutor API Changes

This file records public API findings from building the language tutor. The
former small consumer has been retired; the surviving implementation is
`examples/language_tutor_reference_app`.

## Current pass

No new `ai_tools` public API changes are required by the surviving reference
application.

Its shared boundary is built from existing public surfaces:

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
