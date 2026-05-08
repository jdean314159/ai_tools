# ai_tools quality cleanup plan

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

This document is the implementation plan for the next stabilization thread.

The current problem is not just one failing import. The repo has accumulated mixed package layouts, root-level import workarounds, incomplete facade migration, and publication-hygiene drift. These should be cleaned in a controlled order.

## Quality principle

A fresh clone should be able to do the following without manual `PYTHONPATH` tricks:

1. create a fresh virtual environment
2. install packages in editable mode
3. import each package from its real package implementation path
4. run package tests and selected cross-package tests
5. run publication hygiene checks before release snapshots

## Current top risk

The repo mixes package layouts:

    agent_lib/src/agent_lib
    engram_lite/src/engram_lite
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    rag_lib/src/rag_lib

but also:

    llm_inspector_ui/llm_inspector_ui
    llm_engines/llm_engines
    engram/engram
    language_tutor/language_tutor

This mixed layout allows namespace-package shadowing and makes pytest behavior dependent on path order.

## Phase 1 — Fix the active blocker

### Goal

Make `llm_inspector_ui` import from its real implementation path.

### Work

Convert `llm_inspector_ui` to src layout:

    llm_inspector_ui/src/llm_inspector_ui

Update:

- `llm_inspector_ui/pyproject.toml`
- root `pytest.ini`
- `llm_inspector_ui/conftest.py`
- root `conftest.py` only if needed temporarily

### Done when

This command reports a concrete `__file__` under `llm_inspector_ui/src/llm_inspector_ui/__init__.py` and `has describe_ui: True`:

    PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
    import llm_inspector_ui
    print(llm_inspector_ui)
    print('file:', getattr(llm_inspector_ui, '__file__', None))
    print('has describe_ui:', hasattr(llm_inspector_ui, 'describe_ui'))
    PY

And this test passes:

    PYTHONDONTWRITEBYTECODE=1     python -m pytest -c pytest.ini --rootdir=. -q       llm_inspector_ui/tests/test_interop.py -x --tb=short

## Phase 2 — Establish editable-install validation

### Goal

Make editable installs the normal validation path instead of manual `PYTHONPATH`.

### Work

In a clean virtual environment, install packages in dependency order:

    python -m pip install -e ./llm_harness_core
    python -m pip install -e ./llm_engines
    python -m pip install -e ./engram
    python -m pip install -e ./engram_lite
    python -m pip install -e ./llm_inspector
    python -m pip install -e ./rag_lib
    python -m pip install -e ./llm_inspector_ui
    python -m pip install -e ./language_tutor
    python -m pip install -e ./agent_lib

Then test package imports:

    python - <<'PY'
    import agent_lib
    import engram
    import engram_lite
    import llm_engines
    import llm_harness_core
    import llm_inspector
    import llm_inspector_ui
    import rag_lib
    print('imports ok')
    PY

### Done when

All installed packages import without root `PYTHONPATH` manipulation.

## Phase 3 — Reduce root import shims

### Goal

Remove import behavior that makes tests pass only because root `conftest.py` rewrites import state.

### Work

Review and shrink:

- root `conftest.py`
- package-local `conftest.py` files
- root `pytest.ini` `pythonpath` entries
- test scripts that prepend package paths

Do not remove a shim until editable-install tests prove the replacement works.

### Done when

Root `conftest.py` is limited to actual pytest configuration, not package import enforcement.

## Phase 4 — Strengthen hygiene checks

### Goal

Make local artifacts visible before they reach GitHub or a handoff archive.

### Work

Update `scripts/check_publication_hygiene.py` so it fails on unapproved instances of:

- `.pytest_cache/`
- `__pycache__/`
- `*.pyc`
- `*.pyo`
- `*.egg-info/`
- `*.bak`
- `*.orig`
- `*.rej`
- ad hoc `*.patch` files
- local DB files unless explicitly allowed
- local artifacts directories unless explicitly allowed

### Done when

The hygiene checker detects stale patch/reject/cache/build artifacts and the GitHub checklist names the same expectations.

## Phase 5 — Resolve the `engram_lite` boundary

### Goal

Make code reality match the documented decision in ADR-007, or amend ADR-007.

### Current inconsistency

ADR-007 and `PACKAGE_ROLES.md` say `engram_lite` is a curated facade over `engram`, but `engram_lite` still appears to contain substantial implementation code.

### Preferred direction

Keep ADR-007 and finish the facade migration.

`engram_lite` should retain only a small public API, compatibility shims, and any intentionally lite-specific command-line or configuration surface. Canonical implementation should live in `engram`.

### Done when

- `engram_lite` public API contract tests pass
- downstream imports still work through compatibility shims where needed
- duplicated implementation modules are either removed or explicitly justified
- docs, tests, and code all describe the same boundary

## Phase 6 — Convert remaining non-src packages

### Goal

Unify package layout across the repo.

### Work

After `llm_inspector_ui` is stable, consider converting these packages in separate small PRs or commits:

    llm_engines/src/llm_engines
    engram/src/engram
    engram/src/engram_ui
    language_tutor/src/language_tutor

Do not convert all at once unless tests are already reliable.

### Done when

Every importable package follows one layout policy and package metadata agrees with that layout.

## Phase 7 — Refactor oversized modules only after tests are stable

Large modules are a maintainability risk, but they are not the first cleanup target.

Candidate later refactors:

- `engram/engram/project_memory.py`
- `engram/engram/rtrl/core.py`
- `engram/engram_ui/app.py`
- `engram/engram_ui/model_management.py`
- `engram/engram/engine/model_manager.py`
- `engram_lite/src/engram_lite/project_memory.py`
- `agent_lib/src/agent_lib/programming.py`

Do not split these during the packaging stabilization pass unless a test failure forces it.

## Non-goals for the next thread

The next thread should not add new product features. Its job is to make the repo boring to install, import, and test.
