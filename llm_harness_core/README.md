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

## Durable run artifacts

The package owns the dependency-free common envelope for durable generation,
agent-run, and experiment artifacts. Producer-specific bodies and adapters stay
in their producer packages.

```python
from llm_harness_core import load_artifact, summarize_artifact

artifact = load_artifact("unified-run-record.json")
print(summarize_artifact(artifact))
```

Validate and summarize a JSON artifact without importing its producer:

```bash
python -m llm_harness_core.run_artifacts_cli unified-run-record.json
```

Envelope validation does not imply that the reader understands an unknown body
or profile version. Use `body_support_status(...)` with the contracts supported
by the consuming application before interpreting body fields. Privacy metadata
is a declaration for downstream policy, never an export authorization.

Portable local-directory bundles use `write_artifact_bundle(...)` and
`load_artifact_bundle(...)`. The writer creates a previously absent directory,
verifies SHA-256 over the exact attachment bytes, and refuses path escape or
overwrite. Loading computes attachment resolution without mutating the stored
record:

```python
from llm_harness_core import load_artifact_bundle

bundle = load_artifact_bundle("campaign-bundle")
print([item.status for item in bundle.resolutions])
```

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

Memory experiments can use the deterministic staged evaluator to distinguish
storage, retrieval, prompt composition, inference, and exact-scoring failures
without an oracle model or LLM judge:

```python
from llm_harness_core import MemoryCaseSpec, MemoryCaseObservation, evaluate_memory_case

evaluation = evaluate_memory_case(
    MemoryCaseSpec(
        case_id="region_update", expected_storage_count=2,
        required_evidence_ids=("current",), forbidden_evidence_ids=("obsolete",),
        expected_output={"value": "eu-central-1", "evidence_id": "current"},
    ),
    MemoryCaseObservation(
        stored_count=2, retrieved_evidence_ids=("current",),
        prompt_evidence_ids=("current",),
        observed_output={"value": "eu-central-1", "evidence_id": "current"},
    ),
)
print(evaluation.primary_failure_stage)
```

`build_memory_experiment_body(...)` omits raw prompts, memory text, and model
outputs by construction. `prepare_new_artifact_path(...)` enforces the common
no-overwrite rule for frozen runs.

## Synthetic data utilities

`llm_harness_core` includes lightweight synthetic data helpers for memory and retrieval labs:

- `SyntheticDataConfig`
- `generate_memory_records(...)`
- `generate_retrieval_documents(...)`
- `generate_synthetic_bundle(...)`
- `write_synthetic_bundle(...)`

These are intended for small evaluation corpora with `clean`, `noisy`, and
`adversarial` presets.
