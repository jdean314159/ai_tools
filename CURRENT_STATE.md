# Current State

Last updated: 2026-05-09

## Summary

The repo has completed the main packaging/import-stabilization checkpoint. The previously direct-layout packages that were causing import ambiguity have been converted to normal `src/` layout, and the broad package-local validation gate has passed after the `engram` package-surface fix.

Converted packages:

- `llm_engines` now resolves from `llm_engines/src/llm_engines`.
- `language_tutor` now resolves from `language_tutor/src/language_tutor`.
- `engram` now resolves from `engram/src/engram`.
- `engram_ui` now resolves from `engram/src/engram_ui`.

The repository should now be treated as a normal editable-install monorepo. Do not rely on production `PYTHONPATH` path injection to make package imports work.

## Validation checkpoint

Recent successful broad gate:

    1701 passed, 23 skipped in 937.49s

The gate included:

    tests/test_import_provenance.py
    llm_engines/tests
    language_tutor/tests
    agent_lib/tests
    engram_lite/tests
    llm_inspector_ui/tests
    llm_inspector/tests
    rag_lib/tests
    llm_harness_core/tests
    engram/tests --run-engram

Publication hygiene passes after removing generated local artifacts such as `.pytest_cache`, `__pycache__`, `*.pyc`, and editable-install metadata such as `*.egg-info`.

## Important package-surface fix already made

After converting `engram` to `src/` layout, the broader test gate exposed that `engram.engine` was not reachable as a root package attribute because `engram/src/engram/__init__.py` has a custom lazy `__getattr__` implementation. That was fixed so tools such as `pytest.monkeypatch` and normal callers can resolve:

    engram.engine.config_loader

This was the right kind of fix because it restores expected Python package behavior rather than adding test-specific path hacks.

## Known remaining quality issue

The full `engram` gate passed, but these warnings appeared during/after test execution:

    Episode ingestion failed: Query error: Database error: error returned from database: (code: 1032) attempt to write a readonly database
    Deduplication check failed: Query error: Database error: error returned from database: (code: 1032) attempt to write a readonly database

These are not packaging failures. They are runtime-lifecycle warnings. The likely cause is a late write attempt after `ProjectMemory.close()` has already marked the instance closed or after the underlying SQLite/Chroma resource has entered a read-only/teardown state.

The next work item is to add lifecycle guards around late writes, not to suppress all database exceptions.

## Active next step

Add a small closed-state guard in:

    engram/src/engram/memory/ingestion.py
    engram/src/engram/project_memory.py

Specifically:

- In `MemoryIngestor.apply(...)`, return early if `self.project_memory._closed` is true.
- In `ProjectMemory.store_episode(...)`, return early if `self._closed` is true.

Then rerun the focused `engram` gate, the broad gate, and publication hygiene.

## Do not do next

Do not resume feature expansion yet. Avoid new agent behavior, new teaching decks, new UI work, or new RAG labs until the lifecycle warning cleanup is committed and docs are revalidated.
