# ai_tools — ADR Index

<!-- AI_TOOLS_CLEANUP_CHECKPOINT_START -->
## Current cleanup checkpoint

Packaging/import/test stabilization has reached a green checkpoint.

Latest validated broad gate:

    833 passed, 37 skipped in 34.90s

Validated with:

    unset PYTHONPATH
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    PYTHONDONTWRITEBYTECODE=1
    -W error

The earlier `llm_inspector_ui` namespace/import blocker is resolved. Package-local import bootstraps have been removed. Import provenance is now guarded by `tests/test_import_provenance.py`.

Root `conftest.py` still contains a centralized transitional pytest bootstrap. This is intentional while the repo still has mixed package layouts and same-name outer project directories. Do not reintroduce package-local `sys.path`, `PYTHONPATH`, `sys.modules`, manual package loaders, or import reload logic.

Current broad gate command:

    unset PYTHONPATH

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
    python -m pytest -c pytest.ini --rootdir=. \
      tests/test_import_provenance.py \
      llm_engines/tests \
      language_tutor/tests \
      agent_lib/tests \
      engram_lite/tests \
      llm_inspector_ui/tests \
      llm_inspector/tests \
      rag_lib/tests \
      llm_harness_core/tests \
      -x --tb=short -W error

Remaining packaging work, in order:

1. Strengthen publication hygiene enforcement.
2. Convert `llm_engines` to `src/` layout.
3. Convert `language_tutor` to `src/` layout.
4. Convert `engram` to `src/` layout later.
5. Remove the transitional root pytest bootstrap only after package layout consistency makes it unnecessary.
6. Resolve whether `engram_lite` is strictly a facade over `engram` or whether ADR-007 must be amended.
<!-- AI_TOOLS_CLEANUP_CHECKPOINT_END -->

## Purpose

This file maps architectural decisions across the `ai_tools` monorepo.

Use it to answer:

- which decisions are already settled
- where the authoritative decision record lives
- which areas still need explicit ADR coverage

`VISION.md` is the architecture baseline. `ADR_INDEX.md` is the decision map.

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

### ADR-007 — `engram_lite` as a Facade Over `engram`

- File: `adr/ADR-007-engram-lite-as-engram-facade.md`
- Status: Accepted, but implementation should be re-verified
- Scope: `engram`, `engram_lite`, workbench defaults
- Decision: `engram_lite` is intended to be a curated/default facade over `engram`.

Implementation warning:

The current code may still contain substantial independent `engram_lite` implementation. The cleanup thread should either finish the facade migration or amend ADR-007. Preferred direction is to finish the facade migration.

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
6. `engram_lite` is intended to be a curated/default facade over `engram` unless ADR-007 is amended.
7. Packaging/import behavior should be standardized rather than repaired with growing path hacks.

## ADRs that may still be needed

### Inspector / observability event taxonomy

Needed to define shared event categories, required fields, severity semantics, provenance, and compatibility policy.

### Agent execution isolation model

Needed before serious `agent_lib` expansion. Should define filesystem, process, network, and worktree boundaries.

### Package import side-effect policy

May be folded into ADR-008 or added later. Should define what may and may not happen at top-level import time.
