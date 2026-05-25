# Repo Status

Last updated: 2026-05-24

Single source of truth for the current `ai_tools` repo state. Use this file
first when starting a new thread or resuming work after a handoff.

## Current posture

The engram freeze and rename is complete:

- `engram/` is the standalone memory library (formerly engram_lite v0.2.0).
  Import path: `engram/src/engram`. PyPI name: `engram`.
- Heavy engram is archived (read-only) at github.com/jdean314159/engram.
- `engram_lite` package no longer exists in the monorepo.
- All library callers (`language_tutor`, `llm_inspector`, `llm_inspector_ui`,
  `agent_lib`) use `import engram`.

`engram_ui` was deleted (ADR-010) as redundant with `llm_inspector_ui`. No
package is currently broken.

Public-API pass (MEMBERSHIP step 3) — in progress:

- Per-package public API defined via `__all__` + scope/quickstart README for
  `llm_engines`, `llm_harness_core`, `engram`, `rag_lib`, `llm_inspector`,
  `llm_inspector_ui`, `agent_lib`.
- `llm_engines`: added core types (`ChatMessage`, `GenerationRequest`,
  `GenerationResponse`, `ChatModel`) to the public surface.
- `engram`: `__all__` trimmed to the public surface; storage/semantic/telemetry
  layers no longer exported from the top level.
- `llm_inspector`: removed stale `EngramLiteAugmenter`/`make_engram_lite`;
  deleted `engram_lite_adapter.py` and its test.
- `llm_inspector_ui`: collapsed the duplicate `engram_lite` augmenter into the
  single `engram` augmenter; removed remaining `engram_lite` UI strings.
- `agent_lib`: `__all__` trimmed to coordination primitives + core programming
  types; benchmark/demo/red-team runners no longer top-level exports; loud
  EXPERIMENTAL notice added.

Agent design guidance for future work captured in
`docs/design/AGENT_BUILD_NOTES.md`.

## Package layout

Packages on `src/` layout:

    agent_lib/src/agent_lib
    engram/src/engram              ← renamed from engram_lite
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

1. **language_tutor acceptance slice (next objective).**
   Hand-build one `language_tutor` capability against the refreshed public API
   as the API acceptance test (MEMBERSHIP step 4). Validates that `engram` and
   `llm_engines` public surfaces are sufficient without reaching into internals,
   and produces the fixed target for the eventual agent loop. See
   NEXT_THREAD_HANDOFF.md for scope and AGENT_BUILD_NOTES.md §7 for rationale.

2. **Promote validated slice into `examples/`**, then repeat for the rest of
   `language_tutor`.

3. **Course split.** Move `course/` to its own repo consuming `ai_tools` as a
   dependency. Mostly mechanical; validated by a local `pip install`, not
   in-repo tests. Can proceed in parallel.

4. **ASC rebuild.** Worker/mentor orchestrator on `agent_lib`. Gated on
   `agent_lib` reaching beta and on ADR-011 (agent execution isolation) being
   accepted. See AGENT_BUILD_NOTES.md §4.

5. **PyTorch optionality and fresh-clone verification.** Carry-over hygiene
   check from a previous pass.

## Notes for next session

- Work from `~/ai_tools`, confirm `git status --short --branch` shows `main`.
- No package is currently broken; `make test-core` should be green.
- Agent work has captured design guidance — read `docs/design/AGENT_BUILD_NOTES.md`
  and ADR-011 before expanding `agent_lib`.
- Decision rule for agent_lib growth: build a capability when a concrete run
  fails without it, not when a design discussion suggests it.
