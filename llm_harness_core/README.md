# llm-harness-core

## Tier: stable

## Scope

Shared interoperability contracts for the ai_tools suite. Provides the common
vocabulary (messages, traces, results, memory records) that other packages
exchange. Does not run inference, manage memory, or perform retrieval.

Intended users: library authors building on the suite, not end users directly.

## Quick start

```python
from llm_harness_core import (
    LLMMessage, Role,
    OperationResult,
    MemoryRecord,
    TraceEvent,
)

# Build a shared message
msg = LLMMessage(role=Role.USER, content="Hello")

# Wrap a result in the shared envelope
result = OperationResult.ok(value={"answer": "42"})

# Create a trace event for an inspection pipeline
event = TraceEvent(
    event_type="retrieval_completed",
    source_package="rag_lib",
    source_component="BM25Retriever",
    payload={"hits": 5},
)
```



`llm_harness_core` is the small shared interoperability layer for the `ai_tools` suite.

## Using this with the rest of the suite

- evaluation guide: [`EVALUATION_WALKTHROUGH.md`](./EVALUATION_WALKTHROUGH.md)
- synthetic-data utilities: see below

This package should stay small, dependency-light, and stable so the rest of the suite can compose around it.

## Current support status

This is a **core** package and an **authoritative** source for shared contracts.

Reach for it when you want to understand how packages in the suite exchange:

- capability descriptors
- messages and tool calls
- retrieved documents and memory records
- operation result / warning / error envelopes
- structured trace events
- evaluator requests and evaluator results

## Position in the stack

`llm_harness_core` sits underneath the higher-level packages:

- `llm_engines` converts backend/model behavior into shared result shapes
- `engram` and `rag_lib` adapt augmentation and retrieval behavior into shared records/events
- `llm_inspector` and `llm_inspector_ui` rely on the shared vocabulary so they can compare systems consistently
- evaluation assets use the shared evaluator protocol to avoid package-local scoring conventions

## Design intent

This package intentionally contains only shared schemas, helper types, and narrow protocols where multiple packages need the same behavioral contract.

It should not absorb:

- backend-specific logic
- UI logic
- retrieval policy
- memory policy
- application-specific behavior

## Evaluation support

The first major behavioral protocol moved here is evaluator support.

That includes:

- evaluator requests
- evaluator results
- thin evaluator wrappers for exact-match, similarity, rubric scoring, and LLM-as-a-judge integration

Use [`EVALUATION_WALKTHROUGH.md`](./EVALUATION_WALKTHROUGH.md) to compare
baseline and augmented systems with a shared vocabulary.

## Synthetic data utilities

`llm_harness_core` includes lightweight synthetic data helpers for memory and retrieval labs:

- `SyntheticDataConfig`
- `generate_memory_records(...)`
- `generate_retrieval_documents(...)`
- `generate_synthetic_bundle(...)`
- `write_synthetic_bundle(...)`

These are intended for small evaluation corpora with `clean`, `noisy`, and
`adversarial` presets.
