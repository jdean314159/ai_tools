# Structural cleanup priorities

**Date:** 2026-08-31
**Status:** Priorities 1–5 complete.

Repository-wide Ruff adoption is complete. The next cleanup phase should target
actual duplication and ownership boundaries rather than broader formatting.

## Priority order

### 1. Remove ignored build and cache artifacts

**Completed 2026-08-31.** The ignored package build/cache/editable-install
artifacts were removed while the virtualenv and recorded evidence were
preserved. Canonical import provenance passed. The post-cleanup canonical gate
was 1,254 passed and 305 skipped before tutor consolidation. The current gate
after tutor consolidation, `reasoning_loop_guard` retirement, and the first
navigation and Pythonic-simplification work is 1,250 passed and 305 skipped.
The explicitly excluded integration tree is 48
passed and one skipped. The former 1,268 count included 14 tests collected from
ignored build copies and is not the canonical-source baseline.

The pre-cleanup workspace contained nine ignored package `build/` trees with 198
copied Python files. Many differ from their canonical `src/` files. It also
contains cache and editable-install metadata directories.

These are not tracked source. Remove only resolved ignored build/cache targets,
then confirm that imports and tests still resolve from canonical `src/` trees.
Do not treat deletion of generated workspace artifacts as a source refactor.

### 2. Consolidate the language-tutor examples

**Completed 2026-08-31.** See
`docs/internal/LANGUAGE_TUTOR_OVERLAP_ASSESSMENT.md` for the grounded
assessment. The smaller duplicate was retired and the full reference app is now
the sole tutor implementation.

The repository maintains both:

- `examples/language_tutor`, a small public-API example; and
- `examples/language_tutor_reference_app`, the canonical full reference app.

Assess their distinct teaching obligations before editing. Prefer one canonical
application implementation. Either reduce the small example to a deliberately
minimal tutorial over canonical components, or retire it and redirect its
teaching material. Do not merge the trees mechanically.

### 3. Replace or retire the reference-app generator

**Completed 2026-08-31.** The stale embedded generator was retired. The
canonical source tree and normal package installation are the supported paths.

`examples/language_tutor_reference_app/create_language_tutor_project.py`
duplicates source, HTML, JavaScript, packaging text, and requirements in embedded
strings. It also retains stale generated-project TODOs.

Prefer generation by copying/packaging the canonical source tree plus small
template assets. If project generation is no longer a supported workflow,
remove it explicitly rather than maintaining a second embedded application.

### 4. Decide the fate of `reasoning_loop_guard`

**Completed 2026-08-31.** The package was retired. Its only validation produced
a false positive on the successful NAV control, it was never integrated, and no
validated within-call reasoning-stream target existed. Frozen validation records
remain as historical evidence; typed action-loop work remains separately owned
by `action_trajectory_loop_guard`.

The text detector is not integrated into NAV and was superseded there by the
typed `action_trajectory_loop_guard`. It remains potentially relevant only for
genuine within-call reasoning streams, a use case not yet validated here.

Choose one disposition: retain it with a concrete experimental target, move it
to an explicitly archival/experimental area, or remove it. Do not imply that
NAV validates it.

### 5. Clarify remaining overlapping contract vocabulary

**Completed 2026-09-01.** The grounded assessment is in
`docs/internal/CONTRACT_BOUNDARY_ASSESSMENT.md`. Agent-runtime and engine-provider
tool contracts remain distinct. Inspector now exports the exact shared
`llm_harness_core.TraceEvent`; its duplicate subclass and copying path were
removed while legacy property aliases were preserved on the shared class.

Review these boundaries without assuming same-named objects are interchangeable:

- `agent_lib.ToolCall` / `ToolResult` versus the `llm_engines` contracts;
- `llm_inspector.TraceEvent` versus `llm_harness_core.TraceEvent`.

Agent-runtime and engine-provider tool contracts may legitimately differ. If
so, document the ownership boundary and use explicit conversion adapters. The
Inspector trace wrapper is the stronger candidate for reduction to a narrow
compatibility adapter or alias.

### 6. Split oversized modules only along proven responsibilities

**First split completed 2026-09-01.** Ground-truth schema loading and snapshot
validation moved from `agent_lib.eval.repo_navigation` to
`agent_lib.eval.navigation_ground_truth`. The original module re-exports every
public name with identical object identity, so callers do not move. This seam
has no dependency on workspace tools, planners, model transports, scoring, or
harness assembly. Further splits remain separate decisions.

**Second split completed 2026-09-01.** The model-tokenization and native
llama-server transport cluster moved to
`agent_lib.eval.navigation_model_transport`. The general configuration error
moved to neutral `agent_lib.eval.navigation_contracts` rather than leaving
transport dependent on the ground-truth module. `repo_navigation` retains
identity-preserving compatibility exports.

**Third split completed 2026-09-01.** Repository confinement, bounded source
tools, post-invocation safety checks, and navigation telemetry moved together to
`agent_lib.eval.navigation_workspace`. Context-history truncation and compaction
moved separately to `agent_lib.eval.navigation_context`. Neither module imports
the planner, scoring, model transport, or harness assembly, and compatibility
exports remain in `repo_navigation`.

**Fourth split completed 2026-09-01.** Prompt and action schemas, token-budget
accounting, planner validation/finalization, and the planner lifecycle hook moved
together to `agent_lib.eval.navigation_planner`. Harness construction consumes
that module, while workspace execution, scoring, and run-record rendering remain
independent. The compatibility facade preserves the original objects.

**Fifth split completed 2026-09-01.** Structured-claim scoring moved to
`agent_lib.eval.navigation_scoring`. Environment manifests, read-only tree
digests, and run-record serialization moved to
`agent_lib.eval.navigation_artifacts`. The scoring module depends only on the
claim, ground-truth, budget, telemetry, and run contracts; artifact construction
does not import the harness at runtime. `repo_navigation` is now harness assembly
and identity-preserving compatibility exports.

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
- the ghost-reference check flags two existing mentions of the legacy Engram
  package name in `ENGRAM_SOURCE_PROVENANCE_REVIEW.md` and the RUN-RECORD
  phase-8 record.

Treat the generated artifacts as priority-1 cleanup. Assess the root metadata
and historical-reference findings separately; do not rewrite historical records
merely to make a string-based check pass.
