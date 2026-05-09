# GitHub Publication Checklist

Last updated: 2026-05-09

## Current publication posture

The repo is closer to publication readiness after the packaging/import stabilization pass. The major direct-layout packages have been converted to `src/` layout, and the broad package-local gate passed.

Recent broad gate:

    1701 passed, 23 skipped in 937.49s

Publication should still wait until the remaining runtime-lifecycle warning in `engram` is fixed and committed.

## Required before publication

### 1. Runtime lifecycle warning cleanup

Fix readonly database warning paths:

    engram/src/engram/memory/ingestion.py
    engram/src/engram/project_memory.py

Use `ProjectMemory._closed` to avoid late writes after close.

### 2. Broad validation

Run:

    unset PYTHONPATH

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1     python -m pytest -c pytest.ini --rootdir=.       tests/test_import_provenance.py       llm_engines/tests       language_tutor/tests       agent_lib/tests       engram_lite/tests       llm_inspector_ui/tests       llm_inspector/tests       rag_lib/tests       llm_harness_core/tests       engram/tests       --run-engram       -x --tb=short -W error

### 3. Remove generated artifacts

Before hygiene or commit:

    rm -rf .pytest_cache
    find . -type d -name '__pycache__' -prune -exec rm -rf {} +
    find . -type f -name '*.pyc' -delete
    find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
    find . -type f -name '*.patch' -delete

### 4. Publication hygiene

Run:

    PYTHONDONTWRITEBYTECODE=1     python scripts/check_publication_hygiene.py

Expected:

    Publication hygiene check passed.

### 5. Status check

Run:

    git status --short

Expected:

- only intentional source/doc changes before commit,
- no `.pytest_cache`, `__pycache__`, `*.pyc`, `*.egg-info`, `*.patch`, or generated tarballs.

## Do not publish if

- broad gate fails,
- publication hygiene fails,
- docs still describe the old `llm_inspector_ui describe_ui` failure as active,
- docs still describe `llm_engines`, `language_tutor`, or `engram` as direct-layout packages,
- readonly DB warnings remain uninvestigated and unexplained.
