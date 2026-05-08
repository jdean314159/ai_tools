# NEXT_STEP.md

Updated: 2026-05-08

## Current state

Packaging/import/test stabilization is green.

Latest broad package-local gate:

    833 passed, 37 skipped in 34.90s

The old immediate blocker is resolved:

    ImportError: cannot import name 'describe_ui' from 'llm_inspector_ui'

The repo now has centralized transitional pytest import control and explicit import provenance tests.

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

## Immediate next increment

Convert `llm_engines` to `src/` layout.

Target structure:

    llm_engines/src/llm_engines

Work in a narrow commit:

1. Move the package directory.
2. Update `llm_engines/pyproject.toml`.
3. Update root `pytest.ini` path entries.
4. Update root `conftest.py` `TEST_SOURCE_PATHS`.
5. Update root `conftest.py` `SOURCE_PACKAGE_EXPECTATIONS`.
6. Update `tests/test_import_provenance.py`.
7. Run editable install validation.
8. Run `llm_engines/tests`.
9. Run the broad gate.

## Validation sequence

    python -m pip install -e ./llm_engines

    cd /tmp

    python - <<'PY'
    import llm_engines
    print(llm_engines.__file__)
    PY

Then from repo root:

    cd /home/cybernaif/ai_tools

    unset PYTHONPATH

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
    python -m pytest -c pytest.ini --rootdir=. \
      tests/test_import_provenance.py \
      llm_engines/tests \
      -x --tb=short -W error

Then run the broad gate.

## Do not do yet

Do not convert `engram` first. It is larger and has more internal assumptions.

Recommended remaining layout order:

1. `llm_engines`
2. `language_tutor`
3. `engram`

## Policy reminder

Do not add package-local path hacks back to package `conftest.py` files. Root `conftest.py` is the only allowed transitional pytest import bootstrap.
