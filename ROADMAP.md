# ai_tools — Roadmap

<!-- AI_TOOLS_STATUS_START -->

## Current state

See `STATUS.md` for the authoritative current state, active work priority list,
and current test gate baseline. The checkpoint blocks below are historical.

<!-- AI_TOOLS_STATUS_END -->

## Purpose

This is the ordered execution plan for the `ai_tools` monorepo.

For the next thread, packaging/import/test stabilization takes precedence over new feature work.

## Planning assumptions

1. `ai_tools` is a local-first modular LLM harness.
2. `ai_tools` is also an educational and diagnostic environment for understanding LLM behavior.
3. `llm_harness_core` is the shared interoperability layer.
4. `llm_inspector_ui` is the main user-facing workbench.
5. A clean install/test story is a release gate, not an optional polish item.

## Phase 0 — Packaging/import stabilization

### Goal

Make the repo boring to install, import, and test.

### Work

- Convert `llm_inspector_ui` to src layout.
- Fix its package metadata and pytest configuration.
- Verify `describe_ui` imports from the real implementation path.
- Establish editable-install validation in a clean virtual environment.
- Correct package install order.
- Reduce root import shims after editable installs are reliable.

### Done when

A fresh environment can install the packages in editable mode and run selected package/cross-package tests without manual `PYTHONPATH` dependence.

## Phase 1 — Publication hygiene

### Goal

Prevent local development artifacts from entering release snapshots or GitHub.

### Work

- Strengthen `scripts/check_publication_hygiene.py`.
- Fail on `.pytest_cache`, `*.egg-info`, `*.bak`, `*.orig`, `*.rej`, ad hoc patches, local DBs, and cache files unless explicitly allowed.
- Add or maintain CI coverage for hygiene.

### Done when

A clean snapshot can pass the hygiene checker without manual inspection.

## Phase 2 — Resolve memory package boundary

### Goal

Make `engram`, `engram_lite`, ADR-007, tests, and docs agree.

### Work

- Decide whether `engram_lite` is strictly a facade or a lightweight independent implementation.
- Preferred: keep it as a facade over `engram`.
- Move duplicated implementation into `engram` or explain why it remains lite-specific.
- Keep compatibility shims where useful, but document removal expectations.

### Done when

`engram_lite` public API contract tests pass and its code structure matches the documented role.

## Phase 3 — Standardize remaining package layouts

### Goal

Bring the rest of the monorepo into one packaging model.

### Work

After `llm_inspector_ui` is stable, convert remaining non-src packages in small steps:

- `llm_engines`
- `engram`
- `language_tutor`

Do not convert all packages at once unless the tests are already reliable enough to catch regressions.

### Done when

All importable packages use a consistent layout and metadata policy.

## Phase 4 — Workbench reliability and teaching value

### Goal

Make `llm_inspector_ui` a reliable teaching and diagnostic workbench.

### Work

- Validate baseline, memory, and RAG flows.
- Improve explanatory UI text.
- Keep `engram_lite` as the default memory path unless intentionally testing full `engram`.
- Add integration tests for visible traces and exported artifacts.

### Done when

A new user can launch the workbench and inspect baseline, memory-augmented, and retrieval-augmented runs.

## Phase 5 — Reference application

### Goal

Make `language_tutor` the canonical example of composing the libraries.

### Work

- Align with modern `llm_engines`.
- Use `engram_lite` by default, with full `engram` optional.
- Expose useful observability hooks.

### Done when

The app demonstrates the current stack rather than older integration patterns.

## Phase 6 — Agent work

### Goal

Proceed with `agent_lib` only after the package foundation is stable.

### Work

- Keep policy and sandbox boundaries explicit.
- Integrate with traces and task manifests.
- Avoid adding orchestration complexity before basic install/test reliability is solved.

### Done when

Agent workflows are inspectable, constrained, and testable.

## Standing rule

Do not add new capabilities on top of unstable package/import behavior. Stabilize the foundation first.
