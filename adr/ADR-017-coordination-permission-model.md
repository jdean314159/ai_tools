# ADR-017: Coordination permission model

**Date:** 2026-06-20
**Status:** Accepted
**Related:** SPEC-COORD-01; COORD gaps 1, 2, and 4

## Decision

`WorkspacePolicy` has an optional `allowed_tools` grant, enforced by the
existing `ProgrammingToolRuntime` policy gate (also exported as
`EnforcingToolRuntime` for control-plane terminology). The check runs before
path and command validation.

The coordination layer remains a constructor of correctly scoped runtimes:

- `build_session_tool_runtime()` copies a session's declared capabilities into
  its runtime grant.
- `build_coordinator_tool_runtime()` uses `allowed_tools=[]` for an explicit
  coordinator deny-all runtime.
- `route_by_capability()` selects the first matching session. Multiple-match
  scheduling is intentionally deferred.

## Invariants

- `allowed_tools=None` leaves the historical unrestricted tool-name behavior
  unchanged.
- `allowed_tools=[]` denies every tool.
- An ungranted tool returns `tool_not_granted` before any path or command
  policy is evaluated.

## Alternatives

1. A parallel permission layer in `coordination.py` was rejected because it
   duplicates the existing execution gate and creates two sources of truth for
   tool authorization.
2. Per-session state embedded in `WorkspacePolicy` execution semantics was
   rejected because workspace configuration and session identity have separate
   lifecycles. The coordinator instead derives a scoped policy per runtime.

## Scope

This closes COORD ledger gaps 1 (capability routing), 2 (per-agent tool
permissions), and 4 (explicit coordinator never-execute guard). Gap 3,
enforced reservations, remains open and is deferred to SPEC-COORD-02.
