# Quality Cleanup Plan

Last updated: 2026-05-09

## Status

The main packaging/import stabilization checkpoint is complete. The repo now has successful broad validation after converting the previously problematic direct-layout packages to `src/` layout and fixing the `engram.engine` root package surface.

Recent broad gate:

    1701 passed, 23 skipped in 937.49s

The next work is not another large package move. The next work is quality cleanup.

## Phase 1 — Runtime lifecycle cleanup

Active.

Problem:

    Episode ingestion failed: attempt to write a readonly database
    Deduplication check failed: attempt to write a readonly database

Likely cause:

    A late write path is running after ProjectMemory.close() or after the underlying DB has entered teardown/read-only state.

Required fix:

- Add a closed-state guard in `MemoryIngestor.apply(...)`.
- Add a defensive closed-state guard in `ProjectMemory.store_episode(...)`.
- Use the existing `ProjectMemory._closed` state.
- Do not hide all DB errors.
- Do not string-match SQLite error messages.

Validation:

    engram/tests --run-engram
    full broad package-local gate
    scripts/check_publication_hygiene.py

## Phase 2 — Import-path cleanup

Goal: remove production path hacks and isolate any remaining path mutation to tests or dev scripts.

Audit command:

    grep -R "sys.path.insert\|sys.path.append\|PYTHONPATH\|pathlib.Path.*parents" -n       --include='*.py'       . | grep -v '.venv' | grep -v '__pycache__'

Expected direction:

- Package code should rely on editable installs and package metadata.
- Tests may use explicit test-only path setup where unavoidable.
- Subprocess CLI tests should pass because packages are installed editable, not because repo-local `PYTHONPATH` leaks into production behavior.

## Phase 3 — Root package API simplification

Highest-risk target:

    engram/src/engram/__init__.py

Reason:

The custom lazy `__getattr__` already caused a package-surface failure for `engram.engine`. The long-term design should make the root package boring and predictable.

Target:

- Expose stable public API only.
- Keep lazy imports table-driven if still needed.
- Let subpackages behave like ordinary Python packages.
- Add package-surface regression tests for expected imports.

## Phase 4 — Documentation consolidation

After the lifecycle fix and import-path audit, update:

    CURRENT_STATE.md
    NEXT_STEP.md
    THREAD_TRANSFER_NOTE.md
    PACKAGE_ROLES.md
    LLM_HANDOFF.md
    GITHUB_PUBLICATION_CHECKLIST.md
    adr/ADR-008-monorepo-packaging-policy.md

Docs should describe the repo as post-packaging-migration and entering quality hardening.

## Phase 5 — Feature work resumes only after quality gates remain clean

Do not restart agent design, teaching material expansion, UI additions, or RAG labs until:

- readonly warning cleanup is committed,
- broad gate remains clean,
- publication hygiene passes,
- docs reflect the current checkpoint.
