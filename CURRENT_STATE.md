# ai_tools — Current State

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

## Snapshot purpose

This file describes the implementation state of the `ai_tools` repo at the start of the packaging/import cleanup thread.

Use it with:

- `VISION.md` for long-term intent
- `QUALITY_CLEANUP_PLAN.md` for the stabilization plan
- `NEXT_STEP.md` for the next concrete action
- `ADR_INDEX.md` and `adr/ADR-008-monorepo-packaging-policy.md` for accepted packaging policy

## Current overall status

Status: WIP stabilization checkpoint.

The repo has a coherent architecture direction, but it is not yet a clean release-ready Python monorepo. The main blocker is packaging/import/test reliability.

The active failure is:

    ImportError: cannot import name 'describe_ui' from 'llm_inspector_ui' (unknown location)

Observed diagnostic:

    <module 'llm_inspector_ui' (namespace) from ['/home/cybernaif/ai_tools/llm_inspector_ui', '/home/cybernaif/ai_tools/llm_inspector_ui']>
    file: None
    has describe_ui: False

Interpretation:

Python is importing the outer `llm_inspector_ui/` directory as a namespace package instead of importing the real implementation package. This is caused by mixed layout and path-order fragility.

## Architecture direction

The high-level architecture remains sound:

- `llm_harness_core` is the shared interop/contracts layer.
- `llm_engines` provides model/backend abstraction.
- `engram` is the full memory runtime and canonical implementation for memory primitives.
- `engram_lite` is intended to be a curated/default facade over `engram`.
- `llm_inspector` provides trace/evaluation/inspection primitives.
- `llm_inspector_ui` is the Streamlit workbench for comparing baseline, memory, retrieval, and later agent runs.
- `rag_lib` provides source-grounded retrieval and QA patterns.
- `language_tutor` is intended to become the reference application.
- `agent_lib` remains strategically important but should come after stabilization.

## Main implementation risk

The repo currently mixes source layouts:

    agent_lib/src/agent_lib
    engram_lite/src/engram_lite
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    rag_lib/src/rag_lib

and non-src layouts:

    llm_inspector_ui/llm_inspector_ui
    llm_engines/llm_engines
    engram/engram
    language_tutor/src/language_tutor

This has caused namespace-package shadowing and pytest behavior that depends on path order.

## Current quality-control target

The next milestone is not a new feature. The next milestone is:

A fresh clone and fresh virtual environment can install the packages in editable mode and run selected package and cross-package tests without manual `PYTHONPATH` dependence or root import forcing.

## Immediate package status

### `llm_inspector_ui`

Status: active blocker.

Problem:

- `from llm_inspector_ui import describe_ui` fails because Python imports the outer directory as a namespace package.

Proper fix:

- convert to src layout at `llm_inspector_ui/src/llm_inspector_ui`
- update package metadata and test configuration
- verify the import resolves to `src/llm_inspector_ui/__init__.py`

### `llm_harness_core`

Status: central dependency-light interop package.

Keep this small and stable. Avoid importing higher-level packages from it.

### `llm_engines`

Status: core model/backend abstraction.

Needs eventual layout standardization and continued cleanup of legacy compatibility surfaces. Installation order should place it before packages that depend on engines.

### `engram`

Status: canonical full memory implementation.

Keep as the implementation home for memory primitives if ADR-007 remains accepted.

### `engram_lite`

Status: documentation says facade; implementation may still contain substantial independent code.

Required follow-up:

- either finish the facade migration
- or amend ADR-007 and docs to admit an independent lightweight implementation

Preferred direction is to finish the facade migration.

### `llm_inspector`

Status: important inspection package.

Keep top-level imports lightweight. Avoid importing optional memory backends at package import time unless they are behind explicit adapters or lazy imports.

### `rag_lib`

Status: useful retrieval/QA package with growing observability role.

Should stay runnable without requiring live model services for basic tests.

### `language_tutor`

Status: intended reference application.

Do not make it the next focus until packaging/import stabilization is green.

### `agent_lib`

Status: highest-risk future package.

Do not expand it until install/import/test behavior is stable.

## Hygiene status

The cleanup thread should assume local artifacts may exist, including:

- `.pytest_cache/`
- `__pycache__/`
- `*.pyc`
- `*.egg-info/`
- `*.bak`
- `*.orig`
- `*.rej`
- ad hoc patch files
- local DB/test artifacts

These are not the main architecture problem, but they should be blocked by publication hygiene before any public release snapshot.

## What should happen next

1. Convert `llm_inspector_ui` to src layout.
2. Validate the active failing UI import/test.
3. Establish editable-install validation in a fresh environment.
4. Shrink root/path import hacks only after editable installs prove reliable.
5. Strengthen hygiene checks.
6. Resolve the `engram_lite` facade boundary.
7. Only then resume feature, teaching, or agent work.
