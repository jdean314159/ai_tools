# Thread transfer note — ai_tools cleanup

New thread starting point:

I am continuing stabilization work on the `ai_tools` repo. Treat the repo docs and working tree as the source of truth. Chat history is incomplete and should not be treated as canonical.

Read these files first, in this order:

1. `VISION.md`
2. `CURRENT_STATE.md`
3. `QUALITY_CLEANUP_PLAN.md`
4. `NEXT_STEP.md`
5. `PACKAGE_ROLES.md`
6. `ADR_INDEX.md`
7. `adr/ADR-008-monorepo-packaging-policy.md`

## Current checkpoint

Packaging/import/test stabilization is green.

Latest broad package-local gate:

    833 passed, 37 skipped in 34.90s

## Work completed

- `llm_inspector_ui` has been converted to `src/` layout and its previous namespace/import blocker is resolved.
- Editable installs work from outside the repo root.
- Root `conftest.py` owns transitional repo-root pytest import behavior.
- Package-local import bootstraps have been removed.
- Import provenance is now tested explicitly in `tests/test_import_provenance.py`.
- Publication hygiene checking was strengthened.
- Transient artifacts such as `.egg-info`, `.pytest_cache`, `.orig`, `.rej`, `.bak`, and local report/artifact directories were removed.
- `engram_lite` embedding compatibility modules now re-export from `engram`.
- `llm_inspector` now normalizes delegated `engram` trace events at the `engram_lite` adapter boundary.

## Current import policy

Root `conftest.py` still contains a centralized transitional pytest bootstrap. This is intentional temporary debt while mixed layouts remain.

Do not add package-local import bootstrapping back to subproject `conftest.py` files.

Avoid:

- `sys.path.insert`
- manual `PYTHONPATH` mutation
- `sys.modules` package replacement
- `importlib.reload`
- `importlib.util.spec_from_file_location` package loading

## Current broad gate

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

Expected result:

    passed / skipped only

## Next task

Convert `llm_engines` to `src/` layout.

Target:

    llm_engines/src/llm_engines

Update:

    llm_engines/pyproject.toml
    pytest.ini
    conftest.py
    tests/test_import_provenance.py

Validate:

    python -m pip install -e ./llm_engines

    cd /tmp

    python - <<'PY'
    import llm_engines
    print(llm_engines.__file__)
    PY

Then rerun the `llm_engines` tests and the broad gate.

## Do not start yet

Do not start new feature work in `agent_lib`, `rag_lib`, teaching materials, UI, or memory internals until the remaining package-layout cleanup is further along.

## Formatting note

When giving commands in future threads, use indented command blocks or plain shell snippets. Avoid closed triple-backtick fences inside pasted terminal or Python blocks.
