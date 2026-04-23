# llm_inspector

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
engram_lite or rag_lib -> llm_inspector -> llm_inspector_ui
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
