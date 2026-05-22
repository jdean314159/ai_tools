# Repo Status

Last updated: 2026-05-22

Single source of truth for the current `ai_tools` repo state. Use this file
first when starting a new thread or resuming work after a handoff.

## Current posture

The engram freeze and rename is complete:

- `engram/` is now the standalone memory library (formerly engram_lite v0.2.0).
  Import path: `engram/src/engram`. PyPI name: `engram`.
- Heavy engram is archived (read-only) at github.com/jdean314159/engram.
- `engram_lite` package no longer exists in the monorepo.
- All library callers (`language_tutor`, `llm_inspector`, `llm_inspector_ui`,
  `agent_lib`) have been migrated to `import engram`.
- `language_tutor` engine imports migrated from `engram.engine.*` to
  `llm_engines`.
- All tests passing (`make test-core`).

One known broken package:

- `engram_ui` still imports from `engram.engine.*` (now archived). It will not
  run until the engine reconciliation migration is complete. This is tracked as
  the next major workstream (see ROADMAP.md Phase engine-reconciliation).

## Package layout

Packages on `src/` layout:

    agent_lib/src/agent_lib
    engram/src/engram              ← renamed from engram_lite
    engram_ui/src/engram_ui        ← broken until engine reconciliation
    language_tutor/src/language_tutor
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    llm_inspector_ui/src/llm_inspector_ui
    rag_lib/src/rag_lib

One package intentionally remains on direct layout:

    llm_engines/llm_engines

## Installation tiers

    make install        # lightweight default, no torch/CUDA required
    make install-ml     # PyTorch-backed neural/local-model extras
    make install-gpu    # CUDA PyTorch + llama.cpp CUDA build path
    make test-core      # default test suite
    make test-ml        # torch-dependent tests

## Validation commands

    make install && make test-core
    python scripts/check_publication_hygiene.py
    python scripts/check_teaching_artifacts.py

    # Verify engram resolves to the standalone
    .venv/bin/python -c "import engram; print(engram.__file__)"
    # Expected: <repo>/engram/src/engram/__init__.py

## Active work — in priority order

1. **engram_ui engine reconciliation**
   Migrate `engram_ui` off `engram.engine.*` to `llm_engines`. Approximately
   7 files, 16 import lines. Deserves its own ADR before starting.
   See: grep results in NEXT_THREAD_HANDOFF.md.

2. **Cosmetic string cleanup in engram**
   `get_stats()` reports `"backend": "engram_lite"`, `version: "0.2.0"`.
   `inspection.py` emits `source_package="engram_lite"`. Update to `"engram"`.

3. **engram_lite console script cleanup**
   Verify old `.venv/bin/engram-lite-*` entries are gone after clean reinstall.

4. **engram_ui facade_backup directory**
   Delete `engram_lite/src/engram_lite_facade_backup/` (safety copy, no longer
   needed).

5. **Root doc sync**
   VISION.md §3.2/3.3, README.md package table — still describe the two-library
   world. Update after engram_ui migration so docs reflect stable final state.

6. **PyTorch optionality and fresh-clone verification**
   Still valid from previous pass. Run after engram_ui migration.

## Notes for next session

- Work from `~/ai_tools`, confirm `git status --short --branch` shows `main`.
- `engram_ui` will fail to import until engine reconciliation is done — this is
  expected and not a regression.
- Before engine reconciliation, read the blast radius grep in
  NEXT_THREAD_HANDOFF.md and write an ADR scoping the migration.
