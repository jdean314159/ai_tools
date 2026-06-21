# ADR-018 — Path Ownership: Two Mechanisms → Unified Authority

**Status:** Accepted; unify PROMOTED (see Amendment 1).
**Date:** 2026-06.
**Context spec:** SPEC-COORD-02 (enforced reservations → unification, ledger gap 3).
**Supersedes:** nothing. **Superseded by:** nothing yet.

---

## Amendment 1 — Promotion trigger fired at design time (supersedes the "Decision" below)

The original decision was to BRIDGE the two mechanisms now and defer unification behind a
promotion trigger. Codex's design review of SPEC-COORD-02 (bridge version) fired that trigger
early — a stronger form of trigger #1: the advisory and enforced records do not merely *risk*
disagreement in some future live run, they **provably disagree under demonstrated interleavings**
found at design time:

- No symmetric release: bridge release frees the advisory record but leaks the lease.
- Conflict-ordering hazard: a plain advisory reservation by A does not stop B's lease acquisition,
  so B writes despite a reported conflict.
- Inverse-ordering hazard: A's pre-existing lease does not stop B's advisory reservation going
  active; returning a replacement conflict object does not repair the stored mailbox record.
- The `SessionMailbox` protocol cannot atomically inspect/reserve/roll-back across arbitrary
  implementations, so the agreement invariant is unmaintainable in general.
- Path identity differs (coordination uses raw strings; leases normalize), so equivalent paths
  yield divergent advisory records but one lease.

Making the bridge safe requires atomic paired-claim, paired-release, canonical-path rules, and
reconciliation for both orderings — i.e. building consistency machinery whose entire purpose is to
compensate for having two records. When the work to make the waypoint safe approaches the work to
build the destination, build the destination.

**Promoted decision:** UNIFY now. The enforced lease becomes the single source of truth, extended
to be scope-aware (carries `thread_id`, `note`, `created_at`, `metadata`). `FileReservation` becomes
a read-model derived from lease state; `reserve_paths`/`active_reservations` are preserved as a view
(same return types, same `.status` semantics) so existing callers and tests stay green. The two
unsafe orderings become *unrepresentable*: one store, one acquire operation, canonicalization once.

Confirmed before promotion (code reads):
- The lease record (`{owner_id, status}`) is thinner than `FileReservation`; unify must move
  `thread_id/note/created_at/metadata` onto the lease. Bounded, not a redesign.
- The advisory store has exactly two consumers — `examples/mode_comparison.py` and two tests — and
  no production subsystem depends on it as an independent source. The read interface can be
  preserved while the backing store changes underneath.

The original deferred-bridge decision and its rationale are retained below for the record, marked
SUPERSEDED.

---

---

## Context

`agent_lib` currently has TWO mechanisms that both answer "who owns write rights to this path":

1. **`PatchOwnership` / `acquire_patch_lease`** (`programming.py`, `WorkspaceIsolationManager`).
   Owner-scoped, persisted to `_leases_path`, **enforced** at the `EnforcingToolRuntime.invoke()`
   gate: a second owner attempting `replace_text` on a held path is denied with `ownership_denied`.
   Built for the ASC-era problem of multiple parallel workers editing one tree.

2. **`FileReservation` / `reserve_paths`** (`coordination.py`). Thread-scoped, richer metadata
   (`note`, `created_at`, `metadata`), **advisory only**: it records a holder and reports
   `status="conflict"` to a second reserver, but prevents nothing. Built later for the
   coordination-layer question "who is working on what" across a team of sessions.

These are organic divergence: two reasonable local decisions made at different times for different
problems that happen to both be about path ownership. No one chose to have two systems.

## The from-scratch architecture (the target)

Built clean, this would be **one ownership authority with two projections**:

- A single enforced claim/lease answering "who holds write rights to this path, in what scope
  (thread, owner), until when (optional TTL)." Source of truth. Enforced at the single `invoke()`
  write gate every write already passes.
- "Reservation" is NOT a separate stored type. It is a **read-model / view** over that authority —
  the advisory, human-readable, thread-scoped presentation of current claims, regenerated on
  demand.

Visibility and enforcement become the same data at two altitudes, not two stores kept in sync.
The decisive advantage: a contradiction between "advisory says A holds it" and "lease says B holds
it" becomes **unrepresentable**, because there is one record.

## Decision (SUPERSEDED by Amendment 1 — retained for the record)

**We are NOT building the unified architecture now.** SPEC-COORD-02 will *bridge* the two
mechanisms (advisory reservation acquires an enforced lease for the same holder/paths), keeping
both types but connecting them so reservations gain real enforcement.

Rationale for deferring unify:

1. **Backward-compat risk.** COORD-01 established a 67-test green baseline resting on the lease
   mechanism's exact current behavior. Reworking it into the source of truth for a second
   subsystem is a high-blast-radius change for a benefit not yet needed.
2. **The helper agent needs enforcement to WORK, not to be clean.** Bridge and unify both deliver
   cross-agent write-prevention. Unify's sole advantage — no sync seam — only pays off at a scale
   the system has not reached.
3. **Discipline: name the failing run before building.** Unify is the most-build option justified
   by an architectural ideal, not a demonstrated failure. That is the speculative-build pattern the
   ASC campaign learned to distrust.

## The debt, recorded explicitly

The bridge introduces the exact risk the target architecture avoids: **two records of ownership
that must stay consistent.** This is a known, accepted debt, not an oversight. The bridge is a
deliberate waypoint toward the unified target, not the destination.

## Promotion trigger (what forces the unify)

Build the unified architecture when ANY of these concrete runs occurs:

1. The advisory reservation and the enforced lease **actually disagree** in a live multi-agent run
   (the sync seam is violated in practice, not in theory).
2. A **third subsystem** needs to ask "who owns this path" and finds two answers it must reconcile.
3. Reservation scope requirements (TTL, hierarchical paths, cross-thread handoff) grow beyond what
   bridging two flat mechanisms can express cleanly.

Until one of these fires, the bridge stands. A future session reading this ADR inherits BOTH the
fact that two mechanisms exist AND the knowledge that this is debt with a named payoff condition —
not a design to preserve.

## Invariants the bridge must hold

- Bridging must not change behavior when `enforce_patch_ownership=False` or no `isolation_manager`
  is present (COORD-01 backward compat).
- `reserve_paths` returning `status="conflict"` must correspond to the lease being denied for the
  same holder/path — the two records must agree at the moment of conflict, which is the one point
  where disagreement would be most harmful.
