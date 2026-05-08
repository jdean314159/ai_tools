# NEXT_STEP.md

Updated: 2026-05-08

## Current task

Continue from the green packaging/import/test stabilization checkpoint.

Latest broad gate result:

    833 passed, 37 skipped in 34.90s

The immediate task is no longer the `llm_inspector_ui` `describe_ui` import failure. That blocker is resolved.

## Current validated command

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

## Immediate next increment

Strengthen publication hygiene enforcement.

Review and update:

    scripts/check_publication_hygiene.py

It should fail on accidental transient artifacts unless explicitly whitelisted:

    .pytest_cache/
    __pycache__/
    *.pyc
    *.egg-info/
    *.bak
    *.orig
    *.rej
    *.patch
    test_reports/
    test_survey_results/
    local_artifacts/

Run:

    PYTHONDONTWRITEBYTECODE=1 \
    python scripts/check_publication_hygiene.py

Then rerun the broad gate above.

## Next package-layout increment

After hygiene is green, convert:

    llm_engines

to:

    llm_engines/src/llm_engines

Update:

    llm_engines/pyproject.toml
    pytest.ini
    conftest.py
    tests/test_import_provenance.py

Validate editable install:

    python -m pip install -e ./llm_engines

    cd /tmp

    python - <<'PY'
    import llm_engines
    print(llm_engines.__file__)
    PY

Then rerun the `llm_engines` package gate and the broad gate.

## Do not start yet

Do not start new `agent_lib`, UI, teaching, RAG, or memory feature work until packaging/hygiene/layout stabilization remains green.

## Current policy

Root `conftest.py` owns transitional pytest import bootstrapping.

Do not add package-local import bootstrapping back to package `conftest.py` files.
