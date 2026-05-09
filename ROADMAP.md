# ai_tools — Roadmap

<!-- AI_TOOLS_STATUS_START -->

## Current operational checkpoint (2026-05-09)

The repo has completed the main packaging/import stabilization pass.

Completed:

- `llm_engines` converted to `src/` layout.
- `language_tutor` converted to `src/` layout.
- `engram` converted to `src/` layout.
- `engram_ui` moved under `engram/src/engram_ui`.
- `engram.engine` root package surface restored after the `src/` conversion.
- Broad package-local gate passed: `1701 passed, 23 skipped in 937.49s`.

Current active priority:

- Fix `engram` readonly database warnings by avoiding writes after `ProjectMemory.close()`.

Next after that:

1. Import-path cleanup and isolation of test-only path mutation.
2. Simplify root package APIs, especially `engram/src/engram/__init__.py`.
3. Revalidate docs and publication hygiene.
4. Resume feature work only after quality gates remain clean.

<!-- AI_TOOLS_STATUS_END -->

<!-- AI_TOOLS_CLEANUP_CHECKPOINT_START -->
## Current cleanup checkpoint

Packaging/import/test stabilization is green.

Latest broad package-local gate:

    833 passed, 37 skipped in 34.90s

Validated under:

    unset PYTHONPATH
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    PYTHONDONTWRITEBYTECODE=1
    -W error

Completed since the previous transfer update:

- `llm_inspector_ui` import/namespace blocker resolved.
- Editable-install model validated from outside the repo root.
- Package-local import bootstraps removed.
- Import provenance is guarded by `tests/test_import_provenance.py`.
- Root `conftest.py` remains as the single centralized transitional pytest bootstrap.
- Publication hygiene checker now rejects transient artifacts such as `.pytest_cache/`, `*.egg-info/`, `*.bak`, `*.orig`, `*.rej`, `*.patch`, `local_artifacts/`, `test_reports/`, and `test_survey_results/`.
- Transient hygiene artifacts were removed.
- `engram_lite` embedding compatibility modules now behave as facade re-exports over `engram`.
- `llm_inspector` normalizes delegated `engram` trace events back to the `engram_lite` adapter boundary while preserving upstream provenance.

Current policy:

- Do not reintroduce package-local `sys.path`, `PYTHONPATH`, `sys.modules`, manual package loaders, or import reload logic.
- Keep root `conftest.py` as temporary centralized test bootstrap until package layout consistency removes the need for it.
- Keep source/layout changes in small, separately validated commits.

Next recommended increment:

1. Convert `llm_engines` to `src/` layout.
2. Update package metadata and import provenance expectations.
3. Validate editable install and package tests.
4. Rerun the broad gate.
<!-- AI_TOOLS_CLEANUP_CHECKPOINT_END -->

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
