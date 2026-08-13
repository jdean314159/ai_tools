# ai_tools — Roadmap

<!-- AI_TOOLS_STATUS_START -->

## Current state

See `STATUS.md` for the authoritative current state, active work priority list,
and current test gate baseline. NAV-VERIFIABLE-00 is complete with an
`inconclusive` frozen verdict; it is not an active tuning campaign.
RUN-RECORD-00 Phase 2 is complete under ADR-021/022. The Phase 3
generation/agent cross-kind proof is next. The checkpoint blocks below are
historical.

<!-- AI_TOOLS_STATUS_END -->

## Purpose

This is the ordered execution plan for the `ai_tools` monorepo.

For the next thread, begin with the bounded RUN-RECORD-00 Phase 3 generation
proof in `docs/projects/RUN-RECORD-00-unified-run-artifacts.md`. Do not pull
inspector, RAG, photo, or course migrations ahead of that proof.

## Planning assumptions

1. `ai_tools` is a local-first modular LLM harness.
2. `ai_tools` is also an educational and diagnostic environment for understanding LLM behavior.
3. `llm_harness_core` is the shared interoperability layer.
4. `llm_inspector_ui` is the main user-facing workbench.
5. A clean install/test story is a release gate, not an optional polish item.

## Phase 0 — Packaging/import stabilization — COMPLETE

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

A fresh environment can install the packages in editable mode and run selected
package/cross-package tests without manual `PYTHONPATH` dependence.

## Phase 1 — Publication hygiene — COMPLETE

### Goal

Prevent local development artifacts from entering release snapshots or GitHub.

### Work

- Strengthen `scripts/check_publication_hygiene.py`.
- Fail on `.pytest_cache`, `*.egg-info`, `*.bak`, `*.orig`, `*.rej`, ad hoc patches, local DBs, and cache files unless explicitly allowed.
- Maintain the publication-hygiene CI gate.

### Done when

A clean snapshot passes the hygiene checker in CI without manual inspection.

## Phase 2 — Resolve memory package boundary — complete

### Goal

Make `engram`, ADR-009, tests, and docs agree.

### Work

- ADR-009 resolved the former split into the single supported `engram` package.
- Keep the standalone implementation as the single supported memory package.
- Retain the old backend string only as an explicit compatibility alias.

### Done when

`engram` public API contract tests pass and its code structure matches the documented role.

## Phase 3 — Standardize remaining package layouts — complete

### Goal

Keep package layout intentional and validated.

### Work

All packages use `src/` layout (ADR-014 completed `llm_engines` migration). Do not reintroduce old top-level import-shadowing trees such as `engram/engram` or `engram/__init__.py`.

### Done when

`tests/test_import_provenance.py` matches the documented layout and a fresh clone imports packages from the expected paths.

## Phase 4 — Workbench reliability and teaching value

### Goal

Make `llm_inspector_ui` a reliable teaching and diagnostic workbench.

### Work

- Validate baseline, memory, and RAG flows.
- Improve explanatory UI text.
- Keep `engram` as the default memory path.
- Add integration tests for visible traces and exported artifacts.

### Done when

A new user can launch the workbench and inspect baseline, memory-augmented, and retrieval-augmented runs.

## Phase 4A — RUN-RECORD-00 unified artifacts — PHASE 2 COMPLETE

### Goal

Give producers and inspection tools a compatible, versioned artifact surface
without discarding existing NAV run-record replay or forcing all experiments
into one schema shape.

### Work

- Completed: inventory and field/privacy crosswalk.
- Completed: ADR-021 semantics and ADR-022 ownership/public API.
- Completed: dependency-free core envelope/reader plus lossless NAV-v1 and ASC
  adapters over one shared agent body.
- Next: Phase 3 generation recorder with deterministic MockEngine fixtures and
  one privacy-safe live-engine maintainer acceptance run.

### Done when

Two distinct producers emit or adapt to validated records, NAV counterfactual
replay remains compatible, and unknown versions and sensitive fields fail
according to the accepted policy.

## Phase 5 — Reference application

### Goal

Make `language_tutor` the canonical example of composing the libraries.

### Work

- Align with modern `llm_engines`.
- Use `engram` as the supported memory implementation.
- Expose useful observability hooks.

### Done when

The app demonstrates the current stack rather than older integration patterns.

## Phase 6 — Agent work

### Design guidance

Before expanding `agent_lib` or starting the ASC rebuild, read
`docs/design/AGENT_BUILD_NOTES.md`. It captures settled reasoning on
co-evolution, the worker/mentor pattern, gated oversight, long-horizon loops,
and context-rot reduction via Engram primitives, plus the cheapest first move.

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

## Course extraction pre-flight

Before extracting course material into a separate repository, decide whether
these package-internal guides remain with their libraries or move with the
course:

- `llm_inspector_ui/WORKBENCH_TEACHING_GUIDE.md`
- `llm_harness_core/EVALUATION_WALKTHROUGH.md`

They remain in place for now because their links are package-internal and do
not create a library-to-course dependency.
