# RUN-RECORD-00 Phase 2 — agent compatibility slice

**Status:** Complete, 2026-08-13.
**Scope:** Shared dependency-free envelope plus NAV-v1 and ASC adapters. This
phase proves compatibility across two agent producers; it does not prove the
generation/agent cross-kind hypothesis.

## Result

The ADR-021 envelope can represent both current agent artifacts without
rewriting either producer or adding a runtime dependency to
`llm_harness_core`. `agent_lib` owns the profile mappings, while the core reader
can validate and summarize common metadata without importing `agent_lib`.

The envelope is materially larger than either legacy header, but adapter
population was direct. No additional storage subsystem, resolver, schema
package, or Pydantic dependency was needed.

## Implemented

- Dependency-free frozen dataclasses for envelope identity, lifecycle,
  versions, relationships, attachments, actors, time, privacy, omissions, and
  executable capability claims.
- JSON conversion, file loading/writing, version-1 envelope validation, generic
  summary, body/profile support assessment, and a module CLI.
- Deterministic NAV-v1 and ASC adapter identities derived from canonical source
  mappings.
- A shared `agent_run` body containing task, status, termination, elapsed time,
  step count and steps, final output, model roles, evaluation, and profile data.
- Reverse mappings proving that the representative NAV and completed ASC
  records lose no source fields.
- Conservative legacy privacy declarations: content categories are declared,
  sensitivity remains `unknown`, and validation remains `not_validated`.

## Compatibility findings

NAV steps remain inline. Existing consumers directly index the flat legacy
shape:

- `agent_lib/examples/nav_counterfactual_finalize.py:25-67`;
- `reasoning_loop_guard/scripts/replay_nav_test_00.py:64-70`;
- `action_trajectory_loop_guard/scripts/replay_nav_test_00.py:17-22`.

The adapter does not replace `run-record.json`; restoring the adapted mapping
produces the original shape consumed by those programs. The grounded NAV
capability is counterfactual finalization through a live external model call,
not deterministic replay.

ASC completed task records map to the same shared body. ASC-specific gaming,
oracle, reasoning, escalation, workspace, and worker/mentor details remain
profile data or evaluation data rather than contaminating the shared agent
contract.

Current legacy artifacts lack execution wall-clock times, recorder identity,
and privacy validation. Adapters explicitly record those absences rather than
fabricating values. The adapter timestamp is declared unknown to keep repeated
adaptation of identical source mappings byte-stable and identity-stable.

## Deliberate limitations

- Only envelope schema version 1 is understood.
- Body interpretation requires a consumer-declared supported-contract set;
  generic envelope validation does not claim body support.
- Attachments are validated structurally, but Phase 2 has no bundle resolver
  because neither selected adapter needs one.
- The adapter digest covers canonical JSON values, not the original file bytes,
  because both adapters accept mappings. A future file-level adapter may add a
  separate source-byte digest.
- ASC timeout entries are campaign checkpoint data, not standalone final
  records. Experiment/checkpoint adaptation remains deferred.
- No redaction engine was built. The artifact records declarations and scoped
  validation evidence only.

## Validation

At this historical checkpoint, package-local tests avoided a repository-root
bootstrap failure. `examples._repo_bootstrap` now exists; current root tests
must be invoked as `python -m pytest` because the bare `pytest` console script
can resolve the repository root too late for centralized example bootstrapping.

```text
llm_harness_core: 17 passed
agent_lib:         153 passed
```

Targeted coverage includes JSON and file round trips, unknown envelope failure,
unknown body support reporting, confined bundle paths, required recorder or
adapter provenance, stable adapter identity, exact NAV/ASC reverse mapping,
inline NAV steps, and conservative privacy declarations.

## Gate

Phase 2's corrected exit criterion is satisfied: two distinct agent producers
share one agent-run body without loss of their source semantics. This is
explicitly not a cross-kind claim. Phase 3 remains responsible for a minimal
generation recorder, MockEngine contract fixtures, common-reader cross-kind
semantics, and live-engine maintainer acceptance.
