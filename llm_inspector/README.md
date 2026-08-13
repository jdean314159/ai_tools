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

## Using this with the rest of the suite

- use it right after `llm_engines`
- then use it to compare memory and retrieval augmentation paths

## Current support status

This is a **core** package, actively maintained. Tier: **beta** (API mostly
settled; see the suite tier definitions in the root README).

## Inspecting durable run artifacts

`llm_inspector` can validate and explain the unified artifacts produced by
`llm_engines` or adapted by `agent_lib`:

```python
from llm_inspector import inspect_artifact_path, render_artifact_inspection

inspection = inspect_artifact_path("generation-record.json")  # or a bundle directory
print(render_artifact_inspection(inspection))
```

The CLI exposes the same library surface:

```bash
llm-inspect artifact show generation-record.json
llm-inspect artifact show campaign-bundle/
llm-inspect artifact compare before.json after.json --format json
```

Supported bodies currently include generation v1, the NAV/ASC agent-run v1
profiles, and the ASC/NAV experiment v1 profiles. Bundle inspection surfaces
missing or modified attachments without printing resolved absolute paths.
Resolved child-run attachments receive separate sanitized summaries, including
explicit scalar evaluation signals when present; prompts, reasoning, tool
payloads, source, and final output are not printed.
Unknown body/profile versions remain envelope-readable but are not interpreted.
Comparisons report label equality separately and never infer that two records
used an identical model without stronger artifact/runtime facts.

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
