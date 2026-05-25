# llm_inspector

## Tier: beta

## Scope

Observability layer for LLM workflows. Normalizes traces from engines, memory
augmentation, and retrieval into a common model so runs can be inspected,
compared, and exported. Does not run inference or manage memory itself.

## Quick start

Inspect a single augmented run:

```python
from llm_inspector import (
    ContextInspector, BaselineAugmenter, make_engram,
    AugmentRequest, Turn, render_comparison,
)

inspector = ContextInspector()
req = AugmentRequest(turn=Turn(role="user", text="What is RAG?"), session_id="s1")

baseline = BaselineAugmenter()
memory = make_engram(base_dir="~/.myapp", project_id="demo")

inspector.add(baseline.augment(req), label="baseline")
inspector.add(memory.augment(req), label="with_memory")

report = inspector.compare()
print(render_comparison(report))
```

Export a report:

```python
from llm_inspector import report_to_json
print(report_to_json(report))
```



`llm_inspector` is the observability layer for the `ai_tools` suite.

Its job is to normalize what happened across engines, memory augmentation, retrieval, and eventually agent workflows, so that humans can inspect and compare behavior.

## Start here if you are learning from this repo

This is the first inspection layer in the teaching path.

- teaching path stage: Stage 2 in [`../LEARNING_PATH.md`](../LEARNING_PATH.md)
- use it right after `llm_engines`
- then use it to compare memory and retrieval augmentation paths

## Current support status

This is a **core** package and is treated as **active and stable**.

## Responsibilities

- trace normalization
- report/export helpers
- evidence/context conversion
- comparison and diff support
- interop conversions into shared result and event objects

## Position in the stack

`llm_inspector` is the bridge between subsystem behavior and human-readable analysis.

Typical composition:

```text
engram or rag_lib -> llm_inspector -> llm_inspector_ui
```

## Interop

`llm_inspector` consumes and exports shared `llm_harness_core` objects.

That includes:

- shared trace events
- shared operation results
- shared memory/evidence records
- shared messages

This keeps the inspection layer from becoming tightly coupled to one memory package or one retrieval format.

## Goal

The package is not just a debugging helper. It is part of the project’s educational purpose: making hidden LLM-system behavior legible.
