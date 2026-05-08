# GitHub publication checklist

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

Use this checklist before publishing or handing off a clean `ai_tools` snapshot.

## 1. Packaging and install validation

Create a fresh virtual environment and install packages in dependency order:

    python -m pip install -e ./llm_harness_core
    python -m pip install -e ./llm_engines
    python -m pip install -e ./engram
    python -m pip install -e ./engram_lite
    python -m pip install -e ./llm_inspector
    python -m pip install -e ./rag_lib
    python -m pip install -e ./llm_inspector_ui
    python -m pip install -e ./language_tutor
    python -m pip install -e ./agent_lib

Then verify imports without manually setting `PYTHONPATH`:

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

## 2. Test validation

Run the package/cross-package suite selected for the current snapshot.

Minimum after the current cleanup:

    PYTHONDONTWRITEBYTECODE=1     python -m pytest -c pytest.ini --rootdir=. -q       llm_harness_core/tests       llm_inspector/tests       llm_inspector_ui/tests       rag_lib/tests       engram_lite/tests

Run focused integration tests as appropriate:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1     python -m pytest -q integration_tests/test_augmenter_spine.py

Only run full-Engram integration paths when intentionally validating the advanced memory path:

    AI_TOOLS_TEST_FULL_ENGRAM=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1     python -m pytest -q integration_tests/test_augmenter_spine.py::test_full_engram_augmenter_normalizes_or_skips_cleanly

## 3. Repository hygiene

Remove or block accidental local artifacts:

- `__pycache__/`
- `*.pyc`
- `*.pyo`
- `.pytest_cache/`
- `*.egg-info/`
- `*.bak`
- `*.orig`
- `*.rej`
- ad hoc `*.patch` files
- temporary local DBs
- generated local test artifacts unless explicitly whitelisted

Clean command before a publication check:

    find . -type d -name '__pycache__' -prune -exec rm -rf {} +
    find . -type f -name '*.pyc' -delete
    find . -type d -name '.pytest_cache' -prune -exec rm -rf {} +

Then run:

    PYTHONDONTWRITEBYTECODE=1 python scripts/check_publication_hygiene.py

## 4. Documentation consistency

Before publication, confirm these files agree:

- `VISION.md`
- `CURRENT_STATE.md`
- `QUALITY_CLEANUP_PLAN.md`
- `ROADMAP.md`
- `PACKAGE_ROLES.md`
- `ADR_INDEX.md`
- `LLM_HANDOFF.md`
- `NEXT_STEP.md`

Specific consistency checks:

- If `engram_lite` is described as a facade, the code and tests should support that.
- If a package uses src layout, its `pyproject.toml` and pytest configuration should agree.
- The README should not promise a cleaner install path than the repo actually supports.

## 5. Teaching repo expectations

Confirm that a new learner can find:

1. the root entry point
2. the learning path
3. the package roles
4. the workbench guide
5. the evaluation walkthrough
6. the reference application path

Do not expand teaching materials while package imports are broken.

## 6. Final release sanity checks

- fresh clone works
- fresh venv works
- editable installs work
- package imports resolve to real files, not namespace packages
- selected tests pass
- hygiene check passes
- docs match the working tree
- no local artifacts are included accidentally
