# Pythonic simplification assessment

**Date:** 2026-09-01
**Status:** Initial cleanup implemented; larger candidates require separate seams.

## Completed in this pass

### Remove the duplicate Engram test runner

`engram/run_tests.py` was a second, hand-written test suite and runner. It
mutated `sys.path`, dynamically assembled an import namespace, duplicated tests
already owned by `engram/tests`, and maintained a pytest-free fallback even
though pytest is part of Engram's development dependency set. The root Makefile
already invokes `pytest engram/tests/` directly.

The file was removed. Pytest and the Makefile remain the single test execution
path.

### Consolidate navigation-planner mechanics

`agent_lib.eval.navigation_planner.BudgetedNavigationPlanner` rendered the same
bounded step history twice and implemented the same backend/fallback token
accounting twice. Shared `_context_history(...)` and `_record_usage(...)`
helpers now keep those policies in one place while preserving the emitted
prompts and usage dictionaries.

### Separate programming workspace ownership

`agent_lib.programming_workspace` now owns workspace policy, command-isolation
configuration and helpers, workspace allocation, atomic JSON persistence, and
patch leases. `agent_lib.programming` consumes and re-exports those exact
objects, so existing imports and persisted allocation/lease formats remain
unchanged.

### Separate programming value contracts and durable state

`agent_lib.programming_contracts` now owns the plan, verification, patch,
failure-policy, and programming-task value objects. Durable JSON state and its
lifecycle tracker live in `agent_lib.programming_state`, which depends on those
contracts rather than the runtime facade. `agent_lib.programming` re-exports the
exact original objects. Serialization field names and default behavior were
preserved.

### Simplify Engram budget ownership and live guidance

`engram.types` previously imported the large `project_memory` implementation
only to rename `PromptBudget` as the public `TokenBudget`. `TokenBudget` is now
defined in the lightweight types module, while `project_memory.PromptBudget`
remains an identity-preserving compatibility alias. Live messages now name the
current `engram-migrate`, `engram-reconcile`, and `engram[graph]` interfaces.

### Make direct Engram test selection deterministic

The centralized root pytest bootstrap added `engram/src` to `sys.path` but
omitted `engram` from its source-package anchoring table. Direct collection of
`engram/tests` could therefore register the outer project directory as a
namespace package before importing `engram.embeddings`. Engram now participates
in the same explicit source anchoring as the other src-layout packages.

### Separate UI submission policy and presentation

Submission readiness calculation now lives in
`llm_inspector_ui.services.submission`, with direct tests for blocked engines,
no runnable branches, partial readiness, and full readiness. Readiness banners
and chat submission live together in `panels.submission_panel`. The application
module remains the composition root and preserves its imported function names.
The readiness function no longer accepts an unused engine-service argument.

## Confirmed complexity concentrations

### `engram.ProjectMemory`

`engram/src/engram/project_memory.py` owns persistence, sessions, extension
layers, episode storage, temporal state, trust review, retrieval, prompt
composition, lifecycle deletion, and statistics. These are real responsibility
clusters, but they share substantial mutable state. The first state-access
review found no honest large extraction: JSONL persistence, session loading,
episode normalization, vector state, and trust/temporal updates share mutable
episode state. File size alone is not enough justification.

### Remaining `agent_lib.programming` responsibilities

After the workspace and state extractions,
`agent_lib/src/agent_lib/programming.py` still combines tool execution, runtime
configuration, failure control, and context compaction. These remaining pieces
interact at harness construction and no further seam has yet been established.

### `llm_inspector_ui.app`

`llm_inspector_ui/src/llm_inspector_ui/app.py` still combines session
initialization, sidebar controls, transcript rendering, inspection panels, and
the application entry point. UI extraction should continue to follow
existing service and panel boundaries rather than create another generic helper
layer.

## Redundancy that should remain for now

- Legacy artifact adapters encode compatibility and privacy behavior; they are
  not ordinary duplicate serializers.
- Historical documents and frozen run records are evidence, not live source to
  normalize.
- Older `typing.List`/`Dict` annotations are stylistically dated but changing
  them repository-wide would create a large, low-value diff without reducing
  runtime complexity.

## Recommended next steps

1. Map `ProjectMemory` state access before selecting a service boundary.
2. Move one cohesive Streamlit rendering area at a time into an existing panel
   or service module, with UI tests around the moved behavior.
3. Reassess the remaining programming runtime only from a concrete dependency
   or maintenance problem; do not split the facade for size alone.
