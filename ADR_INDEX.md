# ai_tools — ADR Index

<!-- AI_TOOLS_CLEANUP_CHECKPOINT_START -->
## Current cleanup checkpoint

Packaging/import/test stabilization is green.

Latest broad package-local gate:

    833 passed, 37 skipped in 34.90s

Validated under:

    unset PYTHONPATH
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    PYTHONDONTWRITEBYTECODE=1
    -W error

Completed since the previous transfer update:

- `llm_inspector_ui` import/namespace blocker resolved.
- Editable-install model validated from outside the repo root.
- Package-local import bootstraps removed.
- Import provenance is guarded by `tests/test_import_provenance.py`.
- Root `conftest.py` remains as the single centralized transitional pytest bootstrap.
- Publication hygiene checker now rejects transient artifacts such as `.pytest_cache/`, `*.egg-info/`, `*.bak`, `*.orig`, `*.rej`, `*.patch`, `local_artifacts/`, `test_reports/`, and `test_survey_results/`.
- Transient hygiene artifacts were removed.
- `engram` embedding compatibility modules now behave as facade re-exports over `engram`.
- `llm_inspector` normalizes delegated `engram` trace events back to the `engram` adapter boundary while preserving upstream provenance.

Current policy:

- Do not reintroduce package-local `sys.path`, `PYTHONPATH`, `sys.modules`, manual package loaders, or import reload logic.
- Keep root `conftest.py` as temporary centralized test bootstrap until package layout consistency removes the need for it.
- Keep source/layout changes in small, separately validated commits.

Next recommended increment:

1. Convert `llm_engines` to `src/` layout.
2. Update package metadata and import provenance expectations.
3. Validate editable install and package tests.
4. Rerun the broad gate.
<!-- AI_TOOLS_CLEANUP_CHECKPOINT_END -->

## Purpose

This file maps architectural decisions across the `ai_tools` monorepo.

Use it to answer:

- which decisions are already settled
- where the authoritative decision record lives
- which areas still need explicit ADR coverage

`docs/design/VISION.md` is the architecture baseline. `ADR_INDEX.md` is the decision map.

## Existing ADRs

### ADR-001 — Engine Capability Model

- File: `adr/ADR-001-engine-capability-model.md`
- Status: Accepted
- Scope: `llm_engines`
- Decision: engine capabilities should be explicit rather than assumed.

### ADR-002 — Engine Response Schema

- File: `adr/ADR-002-engine-response-schema.md`
- Status: Accepted
- Scope: `llm_engines`, downstream consumers
- Decision: engine calls should return structured responses rather than plain strings only.

### ADR-004 — Engram Retrieval Policy

- File: `adr/ADR-004-engram-retrieval-policy.md`
- Status: Accepted
- Scope: `engram`
- Decision: retrieval across memory layers needs explicit policy.

### ADR-005 — Persistence & Migration

- File: `adr/ADR-005-persistence-migration.md`
- Status: Accepted
- Scope: `engram`
- Decision: persistence strategy should reflect backend realities.

### ADR-006 — Interoperability Core for the LLM Harness Suite

- File: `adr/ADR-006-interoperability-core.md`
- Status: Accepted
- Scope: suite-wide
- Decision: use a dependency-light shared core, `llm_harness_core`, for cross-package schemas.

### ADR-007 — `engram` as a Facade Over `engram`

- File: `adr/ADR-007-engram-as-engram-facade.md`
- Status: Accepted, but implementation should be re-verified
- Scope: `engram`, `engram`, workbench defaults
- Decision: `engram` is intended to be a curated/default facade over `engram`.

Implementation warning:

The current code may still contain substantial independent `engram` implementation. The cleanup thread should either finish the facade migration or amend ADR-007. Preferred direction is to finish the facade migration.

### ADR-008 — Monorepo Packaging and Import Policy

- File: `adr/ADR-008-monorepo-packaging-policy.md`
- Status: Accepted
- Scope: suite-wide
- Decision: standardize package layout and validation around src layout, editable installs, and minimal path shims.

## Missing number

There is currently no `ADR-003` in the repo snapshot. Do not assume one exists unless it is actually added.

## Settled decisions

Treat these as settled unless a new ADR explicitly reverses them:

1. Engine capabilities are explicit.
2. Engine responses are structured.
3. Engram retrieval policy is explicit.
4. Persistence strategy must match backend realities.
5. `llm_harness_core` is the shared interop layer.
6. `engram` is intended to be a curated/default facade over `engram` unless ADR-007 is amended.
7. Packaging/import behavior should be standardized rather than repaired with growing path hacks.

## ADRs that may still be needed

### Inspector / observability event taxonomy

Needed to define shared event categories, required fields, severity semantics, provenance, and compatibility policy.

### Package import side-effect policy

May be folded into ADR-008 or added later. Should define what may and may not happen at top-level import time.

## ADR-009 — Freeze engram, dissolve engram_lite, rename to engram
**File:** `adr/ADR-009-engram-freeze-and-rename.md`
**Status:** Accepted
**Summary:** Heavy engram archived at github.com/jdean314159/engram. Original
standalone engram_lite implementation restored and renamed to `engram`. ADR-007
superseded. engram_ui engine migration deferred to follow-on ADR.

## ADR-010 — Archive engram_ui, add chat panel to llm_inspector_ui
**File:** `adr/ADR-010-archive-engram-ui-add-chat-panel.md`
**Status:** Accepted
**Summary:** `engram_ui` deleted as redundant with `llm_inspector_ui`. Streamlit
dependency dropped from the active package set. No package broken as a result.

## ADR-011 — Agent execution isolation model
**File:** `adr/ADR-011-agent-execution-isolation.md`
**Status:** Proposed
**Summary:** Frames the filesystem/process/network/worktree boundary decisions
needed before serious `agent_lib` expansion. Recommends enforced (container,
network-default-deny) over advisory confinement. Left Proposed pending the first
real ASC-build run, per the co-evolution rule in AGENT_BUILD_NOTES.
