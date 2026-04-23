# ai_tools — ADR Index

## Purpose of this document

This file is the quick map of architectural decisions that matter across the `ai_tools` monorepo.

Use it to answer:

- which decisions are already settled
- where the authoritative decision record lives
- which areas still need explicit ADR coverage

`VISION.md` is the architectural baseline.
`ADR_INDEX.md` is the map of the decisions that should not be re-litigated casually.

---

## Existing ADRs

## ADR-001 — Engine Capability Model

- **File:** `adr/ADR-001-engine-capability-model.md`
- **Status in file:** Accepted
- **Scope:** `llm_engines`
- **What it decides:**
  - engine capabilities should be modeled explicitly rather than assumed universally
  - callers should not assume every backend supports every feature
  - the engine layer should make capability mismatches visible and structurally meaningful
- **Why it matters:**
  This is the foundation for a serious engine abstraction layer.

---

## ADR-002 — Engine Response Schema

- **File:** `adr/ADR-002-engine-response-schema.md`
- **Status in file:** Accepted
- **Scope:** `llm_engines`, downstream consumers
- **What it decides:**
  - engine calls should return structured responses rather than collapsing everything to raw strings
  - important output details such as metadata and tool behavior should survive the engine boundary
- **Why it matters:**
  This is a prerequisite for observability and structured downstream orchestration.

---

## ADR-004 — Engram Retrieval Policy

- **File:** `adr/ADR-004-engram-retrieval-policy.md`
- **Status in file:** Accepted
- **Scope:** `engram`
- **What it decides:**
  - retrieval across multiple memory layers needs explicit policy rather than ad hoc merging
  - contradictions, precedence, and recency need principled handling
- **Why it matters:**
  Memory quality depends not just on storing information, but on choosing what to surface.

---

## ADR-005 — Persistence & Migration (Minimal)

- **File:** `adr/ADR-005-persistence-migration.md`
- **Status in file:** Accepted
- **Scope:** `engram`
- **What it decides:**
  - different storage layers need different migration expectations and safety assumptions
  - persistence strategy should reflect backend realities rather than pretending every store is equally reversible
- **Why it matters:**
  This helps keep the memory system realistic and maintainable.

---

## ADR-006 — Interoperability Core for the LLM Harness Suite

- **File:** `adr/ADR-006-interoperability-core.md`
- **Status in file:** Accepted
- **Practical implementation state:** implemented and still expanding across multiple packages
- **Scope:** suite-wide
- **What it decides:**
  - the suite should gain a dependency-light shared core (`llm_harness_core`)
  - shared schemas should be used for capabilities, messages, retrieval/memory artifacts, operation results, and trace events
  - foundational packages should be adapted first
- **Why it matters:**
  This is the key architectural move that turns a set of related packages into an actual harness ecosystem.


---

## Missing number

There is currently no `ADR-003` in the repo snapshot.

That is not necessarily a problem, but it should be treated intentionally:

- either the number was skipped on purpose,
- or an earlier decision document was removed,
- or the numbering should be normalized later.

For future continuity, avoid assuming there is an ADR-003 unless one is actually added.

---

## Decisions that should be treated as settled in practice

Even when a future thread starts fresh, these should be treated as effectively settled unless there is a deliberate architectural reversal:

1. `llm_engines` should use explicit capability modeling.
2. Engine responses should be structured, not plain-string-only.
3. Engram retrieval policy should be explicit and principled.
4. Persistence strategy in Engram should match the realities of its storage backends.
5. The suite is moving toward a shared interoperability core, not further package-local divergence.

---

## ADRs that should probably be added next

These are the most obvious gaps in the current decision record.

## Proposed future ADR — Inspector / observability event taxonomy

### Why it is needed

The suite now depends increasingly on shared trace and diagnostics events across:

- memory
- retrieval
- engine execution
- UI/workbench inspection
- eventually agents

A dedicated ADR should define:

- event categories
- required fields by event type
- severity semantics
- provenance expectations
- compatibility policy for old/new trace shapes

---

## Proposed future ADR — `engram` vs `engram_lite` boundary

### Why it is needed

The project now has two memory packages with related but different roles.
A formal ADR should answer:

- what belongs only in `engram`
- what belongs in `engram_lite`
- what the workbench should use by default
- what the reference app should use by default

---

## Proposed future ADR — Agent execution isolation model

### Why it is needed

`agent_lib` is strategically important but safety-critical.
A formal ADR should define:

- filesystem/process/network isolation expectations
- what counts as “sandboxed enough” for the project
- whether sandboxing is mandatory or profile-based
- how isolation interacts with observability and artifacts

---

## Proposed future ADR — Monorepo import and packaging policy

### Why it is needed

The repo now uses lightweight root-level import shims to reduce monorepo import-shadowing issues.
That is practical, but it should be made intentional.

A formal ADR should decide:

- whether root shims are temporary or supported policy
- how editable installs vs wheel installs should behave
- what CI must validate for packaging confidence

---

## Proposed future ADR — Workbench artifact and export model

### Why it is needed

If `llm_inspector_ui` is the main laboratory for the suite, then saved artifacts, traces, exports, and reproducibility deserve an explicit decision record.

A formal ADR should define:

- what gets persisted from a run
- how artifacts are named and versioned
- what is exportable vs internal
- how compare/diff bundles should be stored

---

## How to use this index in future threads

When a future thread starts:

1. read `VISION.md` for the architecture baseline
2. read `CURRENT_STATE.md` for implementation reality
3. read `ADR_INDEX.md` to identify which decisions are already settled
4. open the specific ADR file only when the current task directly touches that decision

This should reduce the amount of re-derivation needed when context gets long or a previous thread is lost.
