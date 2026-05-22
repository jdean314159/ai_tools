# ADR-007: `engram` as a Facade Over `engram`

## Date
2026-05-04

## Status
Accepted

## Deciders
Jeff Dean

## Context

The repo currently maintains `engram` and `engram` as parallel codebases.
Both packages independently implement `memory/`, `project_memory.py`, `interop.py`,
`inspection.py`, and telemetry. `engram` additionally implements its own
`embeddings/`, `storage/`, `semantic/`, `prompting/`, and `retrieval/` modules.

The split was originally pedagogical: `engram` is the default teaching
memory layer (NB 04), while `engram` is the advanced runtime with the RTRL
neural layer, multi-tier persistence, and richer policy surface.

Maintaining two implementations imposes a roughly 2x tax on cross-cutting
changes and creates drift risk: fixes and improvements in `engram` do not
automatically reach the codebase students are taught from. Without an explicit
relationship between the two, `engram` will fossilize.

Three options were considered:

- **(a) Keep parallel codebases.** Status quo. Compounding maintenance cost.
- **(b) Grow `engram` to replace `engram`.** Burns external references
  (`jdean314159/engram` GitHub repo, Medium articles, course notebooks) and
  forces `engram`'s architectural commitments into the lite framing.
- **(c) `engram` becomes a curated facade over a constrained `engram`
  subset.** One implementation underneath, two public surfaces above.

## Decision

Adopt option (c). `engram` becomes a thin facade over `engram`.

The facade contract is the existing `engram/__init__.py` public API.
That public API is the binding agreement with students and downstream users
and may not silently change.

Concretely:

- `engram` will depend on `engram` as a runtime dependency.
- `engram/src/engram/__init__.py` re-exports a curated subset of
  `engram` symbols, preserving current names and signatures.
- Where `engram` exposes a type that `engram` lacks or has under a
  different name, `engram` gains the canonical implementation and
  `engram` re-exports it.
- `engram` retains *only* code that exists for facade discipline:
  its `__init__.py`, version pinning, possibly a small adapter shim layer
  if needed for signature stability, and lite-specific tests that lock the
  public contract.
- All implementation code currently in `engram/src/engram/`
  subpackages (`embeddings/`, `storage/`, `semantic/`, `prompting/`,
  `retrieval/`, `memory/`, `cli/`, `config/`, `concurrency.py`,
  `telemetry.py`, `inspection.py`, `interop.py`, `contracts.py`,
  `project_memory.py`, `utils/`) is reconciled with `engram` and removed
  from `engram`. Where `engram` has a feature `engram` lacks,
  the feature moves to `engram` first, then `engram` re-exports.

The lite invariants — what makes "lite" lite — are not deleted but become
*constraint discipline* rather than separate code:

- No RTRL / neural layer in the lite public API.
- No advanced retrieval policies (filters, verifiers, finetune adapters)
  in the lite public API.
- Default persistence configuration uses the simplest backend
  (`engram` exports `ProjectMemory` configured for SQLite + ChromaDB
  defaults; advanced users instantiate `engram.ProjectMemory` directly
  with richer configuration).
- Dependency footprint of `engram` itself stays small; `engram` is
  the only required dependency, and `engram` is responsible for keeping
  its own optional-dependency surface honest.

## Consequences

Positive:

- One implementation to maintain, test, and evolve.
- Students learn against code that is the same code production users run.
- Lite invariants are enforced by the facade `__init__.py`, which is
  small enough to review at a glance.
- Future architectural work (e.g., the procedural-memory skill matching
  capability) lands in `engram` and reaches `engram` users
  automatically when appropriate.

Trade-offs:

- Bleed-through risk: `engram` exception types, log output, and
  optional-dependency import errors may surface to lite users in ways
  that do not match the lite framing. Mitigation: facade-layer tests
  pin the observable behavior of the lite surface, including error
  types and import-time behavior.
- One-time migration cost. Existing `engram` tests and any
  downstream code that imports from `engram` internals
  (not the public `__init__.py`) will need to update.
- Course NB 04 currently teaches `engram` directly. The facade
  should preserve the public API, so notebook content should not need
  rewriting; this is a non-goal of the migration but a useful check.

## Migration sequence

This sequence is the recommended order; it is not part of the binding
decision and may be revised based on what the migration reveals.

1. Lock the lite public API. Snapshot current `engram/__init__.py`
   exports and signatures into a contract test in
   `engram/tests/test_public_api_contract.py`.
2. Audit `engram` subpackages against `engram` equivalents. For
   each lite module, decide: re-export, lift to `engram` then re-export,
   or facade-only shim.
3. Lift any lite-only features into `engram` (most likely candidates:
   simplified `ProjectMemory` defaults, lite-style augmenter contracts).
4. Replace `engram/src/engram/__init__.py` with re-exports.
5. Delete reconciled `engram` implementation modules.
6. Run the facade contract test, full `engram` test suite, full
   `engram` test suite, and `integration_tests/`.
7. Run NB 04 end-to-end to confirm no student-facing behavior change.
8. Update `PACKAGE_ROLES.md` and `VISION.md` to reflect the new
   relationship.

## Non-goals

- Renaming either package.
- Changing the GitHub repo identity (`jdean314159/engram`).
- Changing the course notebook sequence or default teaching memory layer.
- Exposing the RTRL neural layer or advanced retrieval policy surface
  through `engram`.

## Related ADRs

- ADR-004: Engram retrieval policy (the policy surface that stays
  hidden behind the facade).
- ADR-005: Persistence migration (the persistence layer the facade
  configures with simple defaults).
- ADR-006: Interoperability core (the shared-types layer both packages
  already depend on; unaffected by this decision).
