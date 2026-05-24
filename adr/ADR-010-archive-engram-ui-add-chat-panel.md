# ADR-010: Archive engram_ui; Add Chat Panel to llm_inspector_ui

**Date:** 2026-05-22
**Status:** Accepted
**Deciders:** Jeff Dean

---

## Context

`engram_ui` was a Streamlit sandbox built against the original heavy `engram`
runtime, predating `llm_inspector_ui`. ADR-009 froze and archived heavy `engram`,
leaving `engram_ui` with broken imports across 7 files (16 import lines against
`engram.engine.*`).

Before committing to migrate those imports to `llm_engines`, the overlap between
`engram_ui` and `llm_inspector_ui` was evaluated:

| engram_ui feature | llm_inspector_ui equivalent | Assessment |
|---|---|---|
| Chat tab | None | Useful; belongs in the workbench |
| Memory inspector | audit_panel, synthesis_panel (partial) | Covered by trace/audit panels |
| Diagnostics bridge | None | Dead — resolves paths via `engram.engine.__file__` |
| Model management | models_panel (capability view only) | Configuration not yet in llm_inspector_ui |

The diagnostics bridge is unrecoverable without significant redesign: it calls
`engram doctor/recommend` internals and resolves config file paths through
`engram.engine.__file__`, which no longer exists.

The model management UI (add/configure engines, profiles) is the only feature
with no current equivalent. It will be addressed as a separate `llm_inspector_ui`
enhancement, not as a reason to keep `engram_ui` alive.

One genuine gap: `llm_inspector_ui` has no chat interface. A user configuring
or debugging the stack needs a quick way to verify an engine is working without
launching a full reference application. A minimal chat panel in the workbench
fills this without requiring `language_tutor`.

---

## Decision

1. **Archive `engram_ui`.** Move it to `docs/history/engram_ui_legacy/` or
   remove it from the monorepo entirely. Do not migrate its `engram.engine.*`
   imports. No new work is spent on it.

2. **Add a Chat panel to `llm_inspector_ui`.** The panel should be minimal and
   diagnostic in intent:
   - "Confirmed: existing two-column layout satisfies the chat requirement. No new panel code required."

3. **Defer model management UI.** Full engine/profile configuration belongs in
   `llm_inspector_ui` eventually, but is out of scope for this ADR. Filed as a
   future Phase 4 item.

---

## Consequences

- `engram_ui` is no longer a broken package requiring maintenance.
- The Streamlit dependency is removed from the monorepo's active package set.
- `llm_inspector_ui` becomes the single UI entry point for all workbench and
  diagnostic needs.
- The Chat panel gives users a fast engine verification path without requiring
  `language_tutor` to be configured.
- Model management configuration remains a gap; users must edit `llm_engines.yaml`
  directly until a future panel is added.

---

## Alternatives considered

**Migrate engram_ui to llm_engines.** Rejected: the diagnostics bridge is
unrecoverable, and the remaining features are either already covered by
`llm_inspector_ui` or belong in `language_tutor`. Migration cost exceeds value.

**Keep engram_ui frozen but in-tree.** Rejected: a broken package that cannot
be imported adds noise to the test suite and publication hygiene checks, and
creates false impressions about the active package set.

**Add full model management to this ADR.** Deferred: scope is too large to
include here. The chat panel is small and immediately valuable; model management
configuration deserves its own planning pass.
