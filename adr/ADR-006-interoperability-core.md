# ADR-006: Interoperability Core for the LLM Harness Suite

## Date
2026-04-21

## Status
Accepted

## Deciders
Jeff Dean

## Context
The monorepo is evolving from a set of related packages into a composable LLM harness ecosystem.
The packages already share overlapping concepts — messages, memory evidence, trace events,
capabilities, and result envelopes — but these concepts currently live in package-specific forms.

## Decision
Introduce a new dependency-light package, `llm_harness_core`, containing only shared schemas:

- `CapabilityDescriptor` / `CapabilityKind`
- `LLMMessage` / `ToolInvocation`
- `RetrievedDocument` / `MemoryRecord`
- `OperationResult` / `OperationWarning` / `OperationError`
- `TraceEvent`

Adapt foundational packages first:

1. `llm_engines` publishes engine descriptors and converts generation responses to `OperationResult`.
2. `engram_lite` publishes memory descriptors and converts prompt-build traces to shared `TraceEvent` objects.

## Consequences
Positive:
- outside users can compose packages with less package-specific glue
- observability can converge on a shared event vocabulary
- future registry/discovery work has a stable cross-package anchor

Trade-offs:
- a new core package adds one more dependency to manage
- package-specific richer types still exist and need staged migration
