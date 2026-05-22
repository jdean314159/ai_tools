# llm_engines

`llm_engines` is the backend and model abstraction layer for the `ai_tools` suite.

It provides a stable way to call LLM backends without forcing the rest of the stack to understand backend-specific quirks.

## Start here if you are learning from this repo

This is the first hands-on package in the teaching path.

- teaching path stage: Stage 1 in [`../LEARNING_PATH.md`](../LEARNING_PATH.md)
- pair it first with `llm_inspector` or `llm_inspector_ui`
- then add `engram` or `rag_lib`

## Current support status

This is a **core** package and is treated as **active and stable**.

## Responsibilities

- engine/backend abstraction
- capability discovery
- normalized generation responses
- backend diagnostics and readiness checks
- failover/fallback support where configured
- interop conversion into shared `llm_harness_core` objects

## Position in the stack

`llm_engines` sits near the bottom of the suite:

- `llm_inspector_ui` uses it for engine/model selection and execution
- `language_tutor` uses it for model access
- `agent_lib` uses it for agent-facing generation
- `llm_inspector` and the UI inspect metadata produced by it

## Architectural notes

Important settled decisions are recorded in:

- `../adr/ADR-001-engine-capability-model.md`
- `../adr/ADR-002-engine-response-schema.md`

Those ADRs mean callers should assume:

- engine capabilities are explicit, not universal
- engine responses are structured, not plain strings only

## Interop

`llm_engines` participates in the shared harness vocabulary through `llm_harness_core`.

Notable interop responsibilities include:

- describing engines with shared capability descriptors
- converting messages/tool calls to shared objects
- converting generation results to shared operation results

## Intended use

Use `llm_engines` when you want a common engine layer underneath memory, retrieval, inspection, or agents.

Do not use it as a dumping ground for UI logic, retrieval logic, or memory policy.
