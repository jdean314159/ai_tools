# Next Step

Last updated: 2026-05-09

## Active checkpoint

Fix the remaining `engram` runtime-lifecycle warning after the successful `src/` layout migration.

The repo has already completed the major packaging conversion for:

    llm_engines
    language_tutor
    engram
    engram_ui

The broad package-local gate has passed:

    1701 passed, 23 skipped in 937.49s

The active issue is not an import failure. It is warning noise from attempted late writes to a readonly database during `engram` runtime/test teardown.

## Problem signature

Observed warnings:

    Episode ingestion failed: Query error: Database error: error returned from database: (code: 1032) attempt to write a readonly database
    Deduplication check failed: Query error: Database error: error returned from database: (code: 1032) attempt to write a readonly database

Known locations:

    engram/src/engram/memory/ingestion.py
    engram/src/engram/project_memory.py

Existing lifecycle state:

    ProjectMemory._closed

## File edit 1

Edit:

    engram/src/engram/memory/ingestion.py

In `MemoryIngestor.apply(...)`, add an early guard immediately after the `outcome` dict is created:

    if getattr(self.project_memory, "_closed", False):
        outcome["skipped_reason"] = "project_memory_closed"
        logger.debug("Skipping ingestion because ProjectMemory is closed")
        return outcome

This prevents ingestion from trying to write after `ProjectMemory.close()`.

## File edit 2

Edit:

    engram/src/engram/project_memory.py

At the beginning of `ProjectMemory.store_episode(...)`, after the docstring and before deduplication, neural scoring, or episodic writes, add:

    if getattr(self, "_closed", False):
        logger.debug("Skipping store_episode because ProjectMemory is closed")
        return ""

This protects direct callers that bypass `MemoryIngestor.apply(...)`.

## Focused validation

Run:

    cd /home/cybernaif/ai_tools
    unset PYTHONPATH

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1     python -m pytest -c pytest.ini --rootdir=.       engram/tests       --run-engram       -x --tb=short -W error

## Broad validation

If focused validation passes, run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1     python -m pytest -c pytest.ini --rootdir=.       tests/test_import_provenance.py       llm_engines/tests       language_tutor/tests       agent_lib/tests       engram_lite/tests       llm_inspector_ui/tests       llm_inspector/tests       rag_lib/tests       llm_harness_core/tests       engram/tests       --run-engram       -x --tb=short -W error

## Hygiene cleanup

Before running publication hygiene or committing:

    rm -rf .pytest_cache
    find . -type d -name '__pycache__' -prune -exec rm -rf {} +
    find . -type f -name '*.pyc' -delete
    find . -type d -name '*.egg-info' -prune -exec rm -rf {} +

    PYTHONDONTWRITEBYTECODE=1     python scripts/check_publication_hygiene.py

## Commit

If tests and hygiene pass:

    git status --short
    git add engram/src/engram/memory/ingestion.py engram/src/engram/project_memory.py
    git commit -m "Avoid engram writes after ProjectMemory close"

## After this checkpoint

After the lifecycle-warning fix is committed, update docs again if needed, then move to import-path cleanup and root package API simplification. Do not start feature work before this small quality checkpoint is complete.
