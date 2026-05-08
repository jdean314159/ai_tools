# Package roles

<!-- AI_TOOLS_CLEANUP_CHECKPOINT_START -->
## Current cleanup checkpoint

Packaging/import/test stabilization has reached a green checkpoint.

Latest validated broad gate:

    833 passed, 37 skipped in 34.90s

Validated with:

    unset PYTHONPATH
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    PYTHONDONTWRITEBYTECODE=1
    -W error

The earlier `llm_inspector_ui` namespace/import blocker is resolved. Package-local import bootstraps have been removed. Import provenance is now guarded by `tests/test_import_provenance.py`.

Root `conftest.py` still contains a centralized transitional pytest bootstrap. This is intentional while the repo still has mixed package layouts and same-name outer project directories. Do not reintroduce package-local `sys.path`, `PYTHONPATH`, `sys.modules`, manual package loaders, or import reload logic.

Current broad gate command:

    unset PYTHONPATH

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
    python -m pytest -c pytest.ini --rootdir=. \
      tests/test_import_provenance.py \
      llm_engines/tests \
      language_tutor/tests \
      agent_lib/tests \
      engram_lite/tests \
      llm_inspector_ui/tests \
      llm_inspector/tests \
      rag_lib/tests \
      llm_harness_core/tests \
      -x --tb=short -W error

Remaining packaging work, in order:

1. Strengthen publication hygiene enforcement.
2. Convert `llm_engines` to `src/` layout.
3. Convert `language_tutor` to `src/` layout.
4. Convert `engram` to `src/` layout later.
5. Remove the transitional root pytest bootstrap only after package layout consistency makes it unnecessary.
6. Resolve whether `engram_lite` is strictly a facade over `engram` or whether ADR-007 must be amended.
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
