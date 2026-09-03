# ADR-019 — Lease Lifecycle: Minimal Recovery Contract

**Status:** Implemented (narrow v1: release lifecycle integration only; owner-death reclaim is a
recorded backlog trigger, not built and not pinned by a test).
**Date:** 2026-06.
**Context spec:** SPEC-LIVE-00 (v8, `6c22fc5`); in-tree forcing evidence is the FX-CONTENTION
fixture in `computer_helper` (`7cb5192`, run artifacts under `runs/live_00_v8_20260624/`).
**Builds on:** ADR-018 (unified path ownership). This is ADR-018 promotion-trigger #3 firing
(lease scope requirements — recovery/TTL — growing beyond what the current flat lease expresses).
**Design input:** `docs/internal/LESSONS_FROM_OPCOM.md` Lesson 1 (lease lifecycle, cross-system).
**Implementation:** `ai_tools` commit `fbf8934` (`feat(agent-lib): expose patch lease release action`)
implements this v1 contract and references this decision commit (`070dbd6`).
**Supersedes:** nothing. **Superseded by:** nothing yet.

---

## What this ADR decides, and what it does NOT

This ADR records the lease-lifecycle decision **forced by a concrete in-tree run** and scopes a
narrow v1. FX-CONTENTION forced the consequence of an *unreleased* lease, so release lifecycle work
is justified now. It did not force a distinct owner-death detector — both workers were live — so
nothing about detection, reclaim, or timeouts is built or obligated by this ADR.

**v1 (Accepted, implement now):** expose and integrate explicit release into the applicable
runtime/worker lifecycle; define and test release ownership and idempotence; add `released_at` for
observability. `release_patch_lease` already exists in the manager, so this is lifecycle integration
and contract definition, not invention.

**Explicitly NOT in v1:** owner-death detection, PID tracking, heartbeat, TTL/`expires_ts`,
automatic reclaim, and `exclusive`/`shared`. The lease model carries no liveness signal (only a
logical `owner_id`), so reclaim would be a separately-designed capability — and crucially, no run
has forced it. It is recorded below as a **backlog trigger**, not as a stated obligation and not
pinned by an xfail test: an xfail would assert the behavior is owed and create an implementation
obligation now, which is exactly the speculative-but-plausible commitment the forcing rule refuses.
The dead-owner gap is real and named; that knowledge lives in the trigger, without an in-tree
artifact pretending a run demanded it.

## Context — the forcing run

ADR-018 unified path ownership: manager-backed coordination uses one enforced lease as the single
source of truth, and a second owner attempting `replace_text` on a held path is denied with
`ownership_denied`. That guard works. FX-CONTENTION exercises it in-tree:

1. `fs_a` performs a no-op `replace_text` (its `old` did not match) — `replaced=False` — but
   **acquires and retains the active lease** (the first permitted dispatch acquires it, no-op included).
2. `fs_b` is explicitly targeted (via the v4 optional `agent` route field) for the same path.
3. `fs_b` receives `ownership_denied` — the ownership guard fires correctly.
4. The authoritative done-check is never satisfied (no canonical value was written).
5. The run reaches `step_cap`.

The denial in step 3 is correct behavior, not a defect. The defect is what has no exit: **`fs_a`
holds a lease it can never release, that never expires, and that no liveness signal can reclaim.**
A legitimate contender (`fs_b`) is therefore blocked indefinitely with no recovery path. That is the
gap — not the denial, the *non-recoverability of the held lease*.

## Why this is in-tree evidence, not a prediction

The earlier disposition treated the lease gap as predicted-not-forced, reading SPEC-LIVE-00 §7
("lease release is explicitly out of scope for this probe") as evidence-absence. That was wrong.
§7 means the probe does not *implement* release — which is precisely why the contender is
permanently stuck. The scope exclusion is the mechanism of the failure, not the absence of one.
FX-CONTENTION is committed in-tree and deadlocks a real contender for want of a recovery contract.

**Disambiguation (keep this distinct from Finding 1).** Predicate D fires for FX-CONTENTION because
the holder remains active, a non-holder write is denied, no permitted contender write occurs, and
done is never satisfied (the committed fixture asserts `result["deadlock"] is True`). It does not
fire for Finding 1, whose done-check is satisfied at step 4. Predicate D classifies termination
state; the lifecycle evidence for THIS ADR is the unrecoverable active lease that produced the
denial — not the predicate-D label itself. The done-check clause is what keeps the two cases
single-sourced: termination (done satisfied, loop overran — SPEC-LIVE-01) and lease lifecycle (done
never satisfied, contender denied by a lease with no recovery path — this ADR) are separated by
whether done was ever satisfied, so they cannot be conflated.

## The state-shape gap (confirmed by code read)

`WorkspaceAllocation` (`programming.py:277`) is `{owner_id, root, isolation_mode, source,
branch_name}`. The lease record persisted to `_leases_path` (`programming.py:416–430`) carries
`{owner_id, status, thread_id, note, created_at, metadata}`. Two precise facts about what is and is
not consumed (code-confirmed):

- **`created_at` is persisted and displayed, but unused for lease lifecycle or enforcement.** It is
  written on acquire, preserved on same-owner reacquisition, and read only to populate
  `FileReservation.created_at` for reservation views/observability (`coordination.py:133`). It is
  never compared to current time; there is no TTL/expiry field, no stale-owner or process-liveness
  reclaim, and no automatic `active`→`released` transition.
- **An explicit release API already exists but is unreachable from the agent loop.**
  `release_patch_lease` (`programming.py:434`) flips a held lease's `status` to `"released"`. So the
  release *mechanism* is present — but it stamps no `released_at` timestamp, and it is **not exposed
  as a LIVE-00 worker action**. Nothing in the worker's action surface, and no obligation in the
  lease contract, causes a no-op or failed holder to call it.

This reframes the gap precisely: FX-CONTENTION does not deadlock because release is *unimplemented*.
It deadlocks because (a) release is not reachable from inside the loop the worker drives, and (b) no
contract obligates the `replaced=False` no-op holder — or a failed holder — to release. There is
also no time- or liveness-based recovery to compensate. The lease has exactly one path out of
`active` today (an owner explicitly calling an API it cannot reach mid-loop), so in practice it has
none.

`docs/internal/LESSONS_FROM_OPCOM.md` Lesson 1 is the cross-system precedent: `expires_ts` (TTL),
`released_ts`, `exclusive`/`shared`, plus reclaim, survived a full Python→TS reimplementation in a
sibling author's system (`mcp_agent_mail` → OPCOM) — load-bearing, not incidental. It is design
input, not a spec to copy: that system is **out-of-process** (TTL-expiry-at-query-time is its only
reclaim option). `agent_lib` is **in-process**, so owner-liveness reclaim is *potentially
implementable* with new instrumentation (a PID, runtime handle, heartbeat, or owner registry) rather
than being limited to a TTL — but note none of that instrumentation exists today (the model carries
only a logical `owner_id`), so liveness is a future design option, not a currently-available
primitive.

## v1 decision (Accepted)

Integrate explicit release into the lease lifecycle. `release_patch_lease` (`programming.py:434`)
already exists in the manager and flips a held lease's `status` to `"released"` — so release itself
is not invented. v1 decides:

- **Lifecycle integration:** expose release as an action reachable inside the loop the worker drives,
  and define *when* a holder releases — specifically the `replaced=False` no-op and the failure
  cases FX-CONTENTION demonstrates. `fs_a`'s no-op is exactly a holder that should yield the lease
  and today has no in-loop way to.
- **Ownership and idempotence:** release affects only a lease the caller actually holds (a
  non-holder release is a no-op, not a steal), and repeated release of an already-released or
  never-held path is a safe no-op. These are defined and tested, not assumed.
- **Observability:** add a `released_at` timestamp so release is visible the way `created_at` is.

The enforcement and persistence plumbing is present; v1 is lifecycle integration + release
ownership/idempotence + a release timestamp. This is the full extent of what FX-CONTENTION forced.

## Explicitly out of v1, and why

- **Owner-death detection, PID tracking, heartbeat, automatic reclaim — NOT built (backlog
  trigger below).** FX-CONTENTION had both workers live; it forced the consequence of an *unreleased*
  lease, not a dead-owner detector. The lease model has no liveness signal to build on
  (code-confirmed): a managed runtime receives only a *logical* `owner_id` (`session.agent_id`,
  `coordination.py:250`); the persisted record (`programming.py:423`) holds that logical ID plus
  `thread_id`, `note`, `created_at`, `metadata` — no PID, runtime-object handle, lease token, or
  heartbeat, and no registry that can answer "is this owner alive?" The store is cross-process locked
  and file-backed (`programming.py:327`), so an in-memory runtime reference is not a valid general
  liveness primitive either. Reclaim is therefore a separately-designed capability (new persisted
  identity/heartbeat semantics, PID-reuse and cross-process handling) — real surface area that no run
  has forced.
- **TTL / `expires_ts` — NOT built, and explicitly NOT a substitute for the unavailable liveness
  signal.** The temptation, once liveness is shown to be expensive, is to reach for a clock-based
  expiry. Resist it: no run has forced a timeout, and a clock is a *worse* answer to the owner-death
  case, not a cheaper one — a wrong TTL either reclaims a live-but-slow holder's lease (corruption) or
  waits out a genuinely-dead owner (the deadlock merely delayed). TTL's unavailability-driven appeal
  is exactly the import-the-precedent trap. Deferred to its own forcing run (a long-hold-timeout
  case), if one ever arises.
- **`exclusive`/`shared` — NOT built.** FX-CONTENTION is purely exclusive-vs-exclusive; shared was
  not forced.

`docs/internal/LESSONS_FROM_OPCOM.md` Lesson 1 (`expires_ts`/`released_ts`/`exclusive` + reclaim,
load-bearing across a Python→TS reimplementation) is cross-system design input for whoever later
builds reclaim — not a spec to copy. That system is out-of-process (TTL-at-query-time is its only
reclaim option); `agent_lib` is in-process, so liveness-based reclaim is the more appropriate design
when a run forces it.

## Backlog trigger (owner-death reclaim)

Recorded as a trigger, NOT as a stated obligation and NOT pinned by an xfail test. An xfail would
assert the behavior is owed and create an implementation obligation now — the speculative-but-
plausible commitment the forcing rule refuses. The dead-owner gap is real and named here; that is
sufficient to preserve the knowledge without an in-tree artifact pretending a run demanded it.

> Revisit automatic reclaim only after a real or probe-forced execution path has a holder terminate
> or become unreachable without an applicable explicit release.

When that path appears, it is the forcing run for the liveness/reclaim capability, and Lesson 1
becomes its design input.

## Test gate

- **FX-RELEASE (release lifecycle) — the v1 gate.** Extends FX-CONTENTION: holder acquires the lease
  and no-ops (or fails), release fires (reachable from the loop), the contender then **re-acquires
  the path and progresses to a satisfied done-check** — the deadlock becomes a completed run. Failing
  today (release is unreachable mid-loop); passing is v1's acceptance criterion.
- **Release ownership and idempotence (unit-level).** A non-holder calling release is a no-op (not a
  steal); repeated release of an already-released or never-held path is a safe no-op. Tested
  explicitly.

Per ADR-018's read-model discipline, the `released_at` addition (and any future state-shape change)
must preserve `reserve_paths` / `active_reservations` return types and `.status` semantics so
existing callers and tests stay green.

No owner-death fixture is added in v1 (see Backlog trigger): the dead-owner path is unforced, and an
xfail asserting it would manufacture an implementation obligation the campaign rule declines to take
on speculatively.

## Out of scope for this ADR

Implementation of owner-liveness reclaim (a separately-designed capability with no forcing run yet;
see Backlog trigger), TTL/`expires_ts` (and any use of TTL as a liveness stand-in), and the
`exclusive`/`shared` data model; anything touching the no-manager advisory mailbox fallback (it
remains advisory-only per ADR-018 and is not an ownership authority). In scope for v1 implementation:
release lifecycle integration plus release ownership/idempotence and `released_at`, gated by
FX-RELEASE.
