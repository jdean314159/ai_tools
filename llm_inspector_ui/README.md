# llm_inspector_ui

## Tier: beta

## Scope

Interactive web workbench for inspecting engine behavior, memory augmentation,
and RAG retrieval. A general-purpose diagnostic tool — run it, do not import it.
Does not expose a programmatic API beyond the two interop helpers in `__init__`.

## Quick start

```bash
cd ai_tools
make run-inspector

# or directly:
python -m llm_inspector_ui
```

Then open http://localhost:8501 in your browser.

The workbench lets you:
- select a backend and model
- run baseline, memory-augmented, and RAG-augmented queries side by side
- inspect what context and evidence reached the model
- export traces for offline analysis
- replay a shared run-artifact JSON file as a read-only Inspector summary



`llm_inspector_ui` is the interactive workbench for the `ai_tools` suite.

It is intended to help users understand and better utilize LLM systems by making engine choice, memory augmentation, and retrieval behavior visible in one place.

## Using this with the rest of the suite

- use it to compare baseline, memory, and retrieval runs
- see [`WORKBENCH_TEACHING_GUIDE.md`](./WORKBENCH_TEACHING_GUIDE.md) for the
  workbench workflow

## Current support status

This is a **core** package, **active**, and still growing as the main human-facing laboratory for the stack.

## Responsibilities

- engine/model selection
- capability display
- run execution and comparison
- prompt/context/evidence inspection
- rendering shared trace events
- viewing memory patterns
- viewing RAG retrieval behavior and diagnostics

## Supported inspection targets

The UI is meant to surface:

- engine capabilities and readiness
- memory augmentation traces
- retrieved evidence and retrieval-stage diagnostics
- final assembled context/prompt shape
- warnings, degraded modes, and selected branches

## Interop role

The UI consumes the shared `llm_harness_core` vocabulary so it can render behavior from multiple packages without bespoke glue for each one.

That includes:

- capability descriptors
- shared trace events
- shared operation results
- retrieved documents and memory records

## Current role in the suite

`llm_inspector_ui` should be treated as the main human-facing laboratory for the stack, not just a thin wrapper around a chat box.

It is where users should be able to compare:

- baseline vs memory augmentation
- memory vs RAG contributions
- retrieval-stage behavior
- eventually, agent planning and tool execution traces


## Beginner-mode support

The Compare and Startup panels now support a **Beginner explanations** mode that adds plain-language guidance for reading prompts, evidence, retrieval diagnostics, and readiness state.
