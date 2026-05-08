# Package roles

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

This file defines the intended role of each package in the `ai_tools` monorepo. It is also a guardrail against over-complication and duplicated responsibility.

## Quality-control note

Package roles are only useful if packaging and imports are boring. During the cleanup thread, role boundaries should be preserved, but the first priority is stabilizing layout, editable installs, and tests.

## Package role table

| Package | Role | Default learner path | Cleanup notes |
|---|---|---:|---|
| `llm_harness_core` | Shared interop contracts: capabilities, messages, operation results, traces, retrieved documents, and memory records. | yes | Keep small and dependency-light. It must not import higher-level packages. |
| `llm_engines` | Model/backend access behind normalized engine capabilities and response schemas. | yes | Eventually standardize layout. Keep backend optionality explicit. |
| `engram` | Full memory runtime and canonical implementation for memory primitives. | after `engram_lite` | If ADR-007 stands, implementation shared by lite belongs here. |
| `engram_lite` | Curated/default facade over `engram` for teaching and small applications. | yes | Current code may not fully match this role. Finish the facade migration or amend ADR-007. |
| `rag_lib` | Retrieval and source-grounded QA patterns with visible evidence flow. | yes | Keep basic tests runnable without live model services. |
| `llm_inspector` | Core trace/evaluation inspection logic and CLI-facing inspection primitives. | yes | Keep top-level imports lightweight; optional adapters should not load heavy dependencies at import time. |
| `llm_inspector_ui` | Streamlit workbench for comparing baseline, memory, retrieval, and later agent runs. | yes | Active blocker. Convert to src layout first. |
| `language_tutor` | Reference application showing how the layers compose into a user-facing tool. | intermediate | Do not prioritize until packaging stabilization is green. |
| `agent_lib` | Inspectable agent orchestration, programming workflow, policy checks, and safety labs. | last | Highest-risk package. Avoid feature expansion until the repo is stable to install and test. |
| `course` | Teaching notebooks, starter projects, and curriculum manifest. | yes | Do not expand teaching assets until the install/test story is stable. |
| `integration_tests` | Cross-package behavioral validation and contract-drift detection. | maintainers | These should prove package boundaries rather than compensate for packaging problems. |

## Stabilization rule

When validation exposes a package deficiency, fix the package deficiency first. Do not paper over package problems with extra teaching docs, path hacks, or duplicated compatibility layers unless the shim is temporary and documented.

## Import rule

A package import should be cheap and predictable.

These should not happen at top-level import time unless explicitly required:

- model discovery
- GPU checks
- ChromaDB initialization
- Streamlit initialization
- database creation
- network calls
- optional backend imports

## Boundary rule

If two packages contain similar implementations, decide which package owns the implementation and which package adapts or re-exports it. Do not allow duplicated implementations to evolve silently.
