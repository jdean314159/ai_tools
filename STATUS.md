# Repo Status

Last updated: 2026-05-09

Single source of truth for "where the repo is right now." Supersedes
CURRENT_STATE.md, NEXT_STEP.md, LLM_HANDOFF.md, and
THREAD_TRANSFER_NOTE.md (all removed). See QUALITY_CLEANUP_PLAN.md for
the multi-phase plan and ROADMAP.md for longer-horizon direction.

## Package layout

Nine packages on `src/` layout:

    agent_lib/src/agent_lib
    engram/src/engram
    engram/src/engram_ui              (under engram/, not its own top-level)
    engram_lite/src/engram_lite
    language_tutor/src/language_tutor
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    llm_inspector_ui/src/llm_inspector_ui
    rag_lib/src/rag_lib

One package intentionally on direct layout:

    llm_engines/llm_engines

`tests/test_import_provenance.py` codifies the direct layout for
`llm_engines`. Earlier handoff docs incorrectly described it as
`src/` layout.

## Validation

Last reported broad gate (before this consolidation):

    1701 passed, 23 skipped in 937.49s

Coverage:

    tests/test_import_provenance.py
    {agent_lib, engram_lite, language_tutor, llm_engines,
     llm_harness_core, llm_inspector, llm_inspector_ui, rag_lib}/tests
    engram/tests --run-engram

Re-run with `-W error` after any change to memory lifecycle:

    unset PYTHONPATH
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
      python -m pytest -c pytest.ini --rootdir=. \
        engram/tests --run-engram -x --tb=short -W error

## Phase 1 lifecycle fix — DONE

Closed-state guards are in the code:

- `MemoryIngestor.apply()` returns early when `project_memory._closed`
- `ProjectMemory.store_episode()` returns early when `self._closed`

The "readonly database" teardown warnings should no longer fire from
these paths.

## Active work, in priority order

1. Doc consolidation (this commit).
2. `engram/src/engram/project_memory.py` is 3,251 lines / 77 methods.
   Extract audit, synthesis, prompt building, and conversation runtime
   into their own modules. Target: ProjectMemory becomes a ~600-line
   facade.
3. `engram/src/engram/__init__.py` still contains the same fragile
   string-matching `__getattr__` chain that previously broke
   `engram.engine`. Drive lazy attributes from one table, delete the
   redundant `if name == "engine"` branch, and add a public-API
   regression test that asserts every name in `engram.__all__` resolves.
4. Root-directory cleanup — see below.
5. `IngestionPolicy` regex patterns (English + Spanish, hardcoded at
   module level) — move to YAML config or replace with the cognitive
   classifier already built.
6. `ProjectMemory.respond()` parameter-filter kludge — fix the engine
   contract instead of papering over it at the call site.

## Root-directory cleanup (item 4 above)

Delete:

    update_ai_tools_md_after_packaging_checkpoint.py   # one-time migration; done
    update_engram.sh                                   # stale
    test_survey_output.txt                             # captured output
    root_pyproject.toml                                # orphaned; each package has its own
    TASKS.json                                         # confirm purpose first

Move:

    ADR_INDEX.md → adr/INDEX.md

Reconsider: AGENT.md, AGENT_FILE_SPEC.md, TASK_MANIFEST_SPEC.md
probably belong in agent_lib/docs/, not at the repo root.

## Open question

Migrate `llm_engines` to `src/` layout for consistency, or codify
direct as final? Current recommendation: codify. `llm_engines` had no
import-ambiguity problem to migrate away from, and the provenance test
already treats direct layout as the contract.

## Deferred until items 1–4 are done

- Skill extraction and matching (the Hermes Agent gap noted in VISION.md)
- agent_lib build-out
- Course modules 3, 6, 8 (sandboxed code execution)
- New RAG labs, agent designs, UI surfaces

The repo is in a quality-hardening phase, not a feature-expansion phase.
