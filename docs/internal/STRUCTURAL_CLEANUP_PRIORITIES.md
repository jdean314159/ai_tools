# Structural cleanup priorities

**Date:** 2026-08-31
**Status:** Proposed next maintenance sequence; no consolidation implemented yet.

Repository-wide Ruff adoption is complete. The next cleanup phase should target
actual duplication and ownership boundaries rather than broader formatting.

## Priority order

### 1. Remove ignored build and cache artifacts

The current workspace contains nine ignored package `build/` trees with 198
copied Python files. Many differ from their canonical `src/` files. It also
contains cache and editable-install metadata directories.

These are not tracked source. Remove only resolved ignored build/cache targets,
then confirm that imports and tests still resolve from canonical `src/` trees.
Do not treat deletion of generated workspace artifacts as a source refactor.

### 2. Consolidate the language-tutor examples

The repository maintains both:

- `examples/language_tutor`, a small public-API example; and
- `examples/language_tutor_reference_app`, the canonical full reference app.

Assess their distinct teaching obligations before editing. Prefer one canonical
application implementation. Either reduce the small example to a deliberately
minimal tutorial over canonical components, or retire it and redirect its
teaching material. Do not merge the trees mechanically.

### 3. Replace or retire the reference-app generator

`examples/language_tutor_reference_app/create_language_tutor_project.py`
duplicates source, HTML, JavaScript, packaging text, and requirements in embedded
strings. It also retains stale generated-project TODOs.

Prefer generation by copying/packaging the canonical source tree plus small
template assets. If project generation is no longer a supported workflow,
remove it explicitly rather than maintaining a second embedded application.

### 4. Decide the fate of `reasoning_loop_guard`

The text detector is not integrated into NAV and was superseded there by the
typed `action_trajectory_loop_guard`. It remains potentially relevant only for
genuine within-call reasoning streams, a use case not yet validated here.

Choose one disposition: retain it with a concrete experimental target, move it
to an explicitly archival/experimental area, or remove it. Do not imply that
NAV validates it.

### 5. Clarify remaining overlapping contract vocabulary

Review these boundaries without assuming same-named objects are interchangeable:

- `agent_lib.ToolCall` / `ToolResult` versus the `llm_engines` contracts;
- `llm_inspector.TraceEvent` versus `llm_harness_core.TraceEvent`.

Agent-runtime and engine-provider tool contracts may legitimately differ. If
so, document the ownership boundary and use explicit conversion adapters. The
Inspector trace wrapper is the stronger candidate for reduction to a narrow
compatibility adapter or alias.

### 6. Split oversized modules only along proven responsibilities

Candidate modules include:

- `agent_lib/eval/repo_navigation.py`;
- `engram/project_memory.py`;
- `engram/neural/core.py`;
- `agent_lib/programming.py`;
- `rag_lib/pipeline.py`.

File size alone is not sufficient justification. Start with
`repo_navigation.py` only if contracts, workspace tools, planning, scoring, and
harness assembly can be separated without introducing circular dependencies or
new public APIs.

## Recommended next assignment

First remove only ignored build/cache artifacts and verify import provenance and
the full test gate. Then perform a read-only language-tutor overlap assessment
that proposes an exact keep/move/delete map before changing either application.

Command-isolation hardening remains a separate capability-validation project;
do not mix it into structural cleanup commits.

## Baseline verification notes

At this handoff:

- `make quality-python` passes for 572 files;
- the Markdown link check passes for 194 files;
- publication hygiene fails on ignored `build`/cache/editable-install artifacts
  and also reports missing root `project.license` / `project.license-files`
  metadata;
- the ghost-reference check flags two existing historical `engram_lite`
  mentions in `ENGRAM_SOURCE_PROVENANCE_REVIEW.md` and the RUN-RECORD phase-8
  record.

Treat the generated artifacts as priority-1 cleanup. Assess the root metadata
and historical-reference findings separately; do not rewrite historical records
merely to make a string-based check pass.
