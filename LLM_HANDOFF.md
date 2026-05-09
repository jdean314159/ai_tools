# LLM Handoff

Last updated: 2026-05-09

## Current state

The ai_tools repo has completed its main packaging/import-stabilization sequence.

Completed and committed:

- `llm_engines` converted to `src/` layout.
- `language_tutor` converted to `src/` layout.
- `engram` converted to `src/` layout.
- `engram_ui` moved under `engram/src/engram_ui`.
- `engram.engine` package-surface fix added after custom `engram.__getattr__` blocked normal attribute resolution.

Broad validation passed:

    1701 passed, 23 skipped in 937.49s

## Current active issue

Readonly database warnings surfaced around `engram` memory writes:

    Episode ingestion failed: attempt to write a readonly database
    Deduplication check failed: attempt to write a readonly database

These warnings did not fail the broad gate. They should still be fixed because they create noisy lifecycle behavior.

Known source locations:

    engram/src/engram/memory/ingestion.py
    engram/src/engram/project_memory.py

Existing lifecycle flag:

    ProjectMemory._closed

## Recommended next patch

Add closed-state guards:

1. In `MemoryIngestor.apply(...)`, return early if `self.project_memory._closed` is true.
2. In `ProjectMemory.store_episode(...)`, return early if `self._closed` is true.

Do not string-match the database error. Do not broadly suppress database errors. Use lifecycle state.

## Validation sequence

Focused:

    unset PYTHONPATH

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1     python -m pytest -c pytest.ini --rootdir=.       engram/tests       --run-engram       -x --tb=short -W error

Broad:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1     python -m pytest -c pytest.ini --rootdir=.       tests/test_import_provenance.py       llm_engines/tests       language_tutor/tests       agent_lib/tests       engram_lite/tests       llm_inspector_ui/tests       llm_inspector/tests       rag_lib/tests       llm_harness_core/tests       engram/tests       --run-engram       -x --tb=short -W error

Hygiene:

    rm -rf .pytest_cache
    find . -type d -name '__pycache__' -prune -exec rm -rf {} +
    find . -type f -name '*.pyc' -delete
    find . -type d -name '*.egg-info' -prune -exec rm -rf {} +

    PYTHONDONTWRITEBYTECODE=1     python scripts/check_publication_hygiene.py

## Engineering guidance

Prioritize small, isolated quality commits. Avoid new feature work until lifecycle warning cleanup is complete and docs remain consistent.
