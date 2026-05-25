# Next Thread Handoff — ai_tools

Last updated: 2026-05-24

## Current state

The engram freeze and rename is complete. `engram_ui` has been deleted
(ADR-010) as redundant with `llm_inspector_ui` — no package is currently
broken. The public-API pass (MEMBERSHIP step 3) is done for all packages.
See STATUS.md for the full per-package picture.

Completed in the most recent session:

- Public API defined per package (`__all__` + scope/quickstart README) for
  `llm_engines`, `llm_harness_core`, `engram`, `rag_lib`, `llm_inspector`,
  `llm_inspector_ui`, `agent_lib`.
- `llm_engines`: core types (`ChatMessage`, `GenerationRequest`,
  `GenerationResponse`, `ChatModel`) added to the public surface.
- `engram`: `__all__` trimmed; storage/semantic/telemetry layers no longer
  exported from the top level.
- Stale `engram_lite` residue removed: `engram_lite_adapter.py` and its test
  deleted; `llm_inspector_ui` duplicate augmenter collapsed into the single
  `engram` augmenter; remaining `engram_lite` UI strings cleaned.
- Agent design guidance captured in `docs/design/AGENT_BUILD_NOTES.md`;
  ADR-011 (agent execution isolation) added as Proposed.
- Doc sync: STATUS, ROADMAP, VISION (§3.2/3.3 facade language corrected to
  match ADR-009), PACKAGE_ROLES, ADR_INDEX brought current.

## Immediate next objective: language_tutor acceptance slice

The next step is the API acceptance test, per MEMBERSHIP step 4: hand-build
**one** `language_tutor` capability against the refreshed public API.

Why this first:

- It validates that the trimmed public surfaces (especially `engram` and
  `llm_engines`) are sufficient to build a real app without reaching into
  internals. If the slice forces a private import, the API is incomplete and
  that is the signal to fix it before the full rebuild.
- It produces the fixed, verifiable target that the eventual worker/mentor
  agent loop should be developed against (see AGENT_BUILD_NOTES §7).
- It is the cheapest move that advances both the examples plan and the agent
  plan at once.

Suggested scope for the slice: pick a single vertical (e.g. ingest a small
vocabulary set, run one tutoring turn through `engram` memory + an
`llm_engines` engine, emit the trace). Harvest domain logic from the existing
`language_tutor/`; rewrite all integration glue against the public API rather
than porting the old imports.

## After the slice

1. If gaps are found, fix the public APIs (small, targeted) and re-run.
2. Promote the validated slice into `examples/`.
3. Repeat for the rest of `language_tutor`; then consider the ASC rebuild,
   gated on `agent_lib` reaching beta (AGENT_BUILD_NOTES §4, ADR-011).
4. Separately, the course split (move `course/` to its own repo consuming
   `ai_tools` as a dependency) can proceed in parallel; it is mostly mechanical
   and validated by a local `pip install`, not in-repo tests.

## Validation

    make test-core

No code logic changed in the most recent session beyond `__all__`/adapter
trims, so the gate should be green. Re-run after the acceptance slice introduces
real consuming code.
