# llm-harness-core

`llm_harness_core` is the small shared interoperability layer for the `ai_tools` suite.

## Start here if you are learning from this repo

Use this package as the architectural reference point, not as the first hands-on package.

- teaching path anchor: [`../LEARNING_PATH.md`](../LEARNING_PATH.md)
- evaluation guide: [`EVALUATION_WALKTHROUGH.md`](./EVALUATION_WALKTHROUGH.md)
- synthetic-data teaching support: see the utilities below

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
- `engram_lite` and `rag_lib` adapt augmentation and retrieval behavior into shared records/events
- `llm_inspector` and `llm_inspector_ui` rely on the shared vocabulary so they can compare systems consistently
- teaching and evaluation assets use the shared evaluator protocol to avoid package-local scoring conventions

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

Use [`EVALUATION_WALKTHROUGH.md`](./EVALUATION_WALKTHROUGH.md) when teaching learners how to compare baseline and augmented systems with a shared vocabulary.

## Synthetic data utilities

`llm_harness_core` includes lightweight synthetic data helpers for memory and retrieval labs:

- `SyntheticDataConfig`
- `generate_memory_records(...)`
- `generate_retrieval_documents(...)`
- `generate_synthetic_bundle(...)`
- `write_synthetic_bundle(...)`

These are intended for small teaching and evaluation corpora with `clean`, `noisy`, and `adversarial` presets.
