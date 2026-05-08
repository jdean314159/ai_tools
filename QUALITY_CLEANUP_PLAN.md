# ai_tools quality cleanup plan

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
