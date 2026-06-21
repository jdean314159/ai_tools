# SPEC-COORD-02 — Enforced Reservations (Probe-First, Then Bridge)

> **WITHDRAWN.** Replaced by [SPEC-COORD-02 — Unified Path Ownership](SPEC-COORD-02-unified-ownership.md)
> under ADR-018 Amendment 1. Retained only as decision history; do not implement this bridge design.

**Status:** Draft for Codex.
**Covers:** Ledger gap 3 (advisory reservations → enforced). Closes the COORD ledger.
**Depends on:** SPEC-COORD-01 (control plane, ed73f04), ADR-018 (ownership target + debt).
**Mode:** Deterministic, two phases — demonstrate the gap, then close it.
**Discipline:** Touches BOTH repos. `agent_lib` change + ADR-018 land in `~/repos/ai_tools`. Probe
lands in `~/repos/computer_helper`. Separate commits. READ the confirmed facts below before coding.

---

## 0. Confirmed facts (assert against these)

From the current `agent_lib`:

- **Enforced ownership already exists.** `WorkspaceIsolationManager.acquire_patch_lease(owner_id,
  paths)` persists leases; a second owner gets `PatchOwnership(status="denied")`. The
  `EnforcingToolRuntime.invoke()` gate (programming.py ~432) calls it on `replace_text` when
  `workspace.enforce_patch_ownership` is True AND `isolation_manager` is not None, denying with
  `error="ownership_denied"`.
- **Advisory reservation is separate.** `reserve_paths(holder, paths, thread_id, note)` in
  coordination.py records a `FileReservation` and reports `status="conflict"` to a second reserver,
  but enforces nothing. `ReservationStatus = Literal["active","released","conflict"]`.
- **The layers already touch one direction.** coordination.py imports `EnforcingToolRuntime` from
  programming.py (the COORD-01 scoped-runtime factory). It does NOT connect `reserve_paths` to
  `acquire_patch_lease`.
- Gap 3 is therefore a **wiring job**, not a build job: the enforcement mechanism exists; the
  coordination layer just doesn't invoke it when a session reserves paths.

ADR-018 records why we bridge (connect the two) rather than unify (one source of truth) now, and
names the trigger that would promote to unify later.

---

## Phase 1 — Demonstrate the disconnect (probe that FAILS to prevent a write)

This is the COORD-00-style move: a deterministic probe whose result documents the exact gap with a
forcing run, before any fix.

**Probe (`computer_helper/probes/coord_probe_02.py`):**

1. Two sessions, `agent_a` and `agent_b`, sharing a workspace with a writable file `shared.py`.
2. `agent_a` calls `reserve_paths("agent_a", ["shared.py"])` → `status="active"`.
3. `agent_b` builds an `EnforcingToolRuntime` (scoped per COORD-01) over the SAME workspace, with
   `enforce_patch_ownership` NOT wired to the reservation (current reality), and issues
   `replace_text` on `shared.py`.
4. **Assert the write SUCCEEDS** — demonstrating the reservation is advisory and prevented nothing.
5. Record this in `COORD_GAP_LEDGER.md` as gap-3 confirmed-by-demonstration: the reservation and
   the enforcement path are disconnected; a reserved path is writable by a non-holder.

Phase 1 is a passing test that asserts the *bad* current behavior, exactly as COORD-00 asserted
advisory-only conflict. It locks in the baseline the bridge must change.

---

## Phase 2 — Bridge: reservation acquires an enforced lease

**`agent_lib` change (under ADR-018):**

1. Add a coordinator-level method that, when a session reserves paths, ALSO acquires a patch lease
   for that holder via an `isolation_manager`. Shape:
   ```python
   # On the coordinator (or a new method that composes the two):
   def reserve_with_enforcement(
       self, holder: str, paths: Sequence[str], *,
       isolation_manager: WorkspaceIsolationManager,
       thread_id: str = "default", note: str = "",
   ) -> list[FileReservation]:
       """Advisory reserve + enforced lease acquisition for the same holder/paths.
       If the lease is denied, the returned reservation carries status='conflict'
       so the advisory record and the enforced record AGREE at the conflict point
       (ADR-018 invariant)."""
   ```
   - Call `reserve_paths` for the advisory record AND `acquire_patch_lease` for enforcement.
   - If `acquire_patch_lease` returns `denied`, the reservation result for that path MUST be
     `status="conflict"` — the two records agree at the one point where disagreement is most
     harmful (ADR-018 invariant).
   - Do NOT change `reserve_paths` itself or `FileReservation`'s schema. The bridge is additive.

2. Backward-compat invariant (ADR-018): existing `reserve_paths` callers and existing
   lease/ownership behavior are unchanged. The bridge is a new opt-in path, not a modification of
   the old one. Existing `agent_lib` tests stay green.

**Probe (Phase 2 assertions, `computer_helper`):**

1. Repeat the Phase-1 scenario but `agent_a` reserves via `reserve_with_enforcement` (with a shared
   `isolation_manager`).
2. **Assert `agent_b`'s `replace_text` on `shared.py` is now DENIED** with `error="ownership_denied"`
   — the reservation now prevents the cross-agent write. This is the result that matters.
3. Assert the agreement invariant: when `agent_b` ALSO tries `reserve_with_enforcement` on
   `shared.py`, its reservation result is `status="conflict"` AND its lease is denied — the advisory
   and enforced records agree.
4. Assert backward compat: a plain `reserve_paths` (no enforcement) still behaves advisory-only
   (Phase-1 behavior preserved for the un-bridged path).

---

## 1. Done criteria

- [ ] ADR-018 present (already written) and linked from the ledger.
- [ ] Phase-1 probe passes (asserts the current advisory-only gap; baseline locked).
- [ ] `agent_lib` bridge method added; existing `agent_lib` suite green (backward compat).
- [ ] Phase-2 assertions pass, especially: cross-agent write DENIED after enforced reservation, and
      the advisory/enforced agreement-at-conflict invariant.
- [ ] `python -m compileall -q` clean both repos; `git diff --check` clean both repos.
- [ ] Library commit (ai_tools) and probe commit (computer_helper) separate.
- [ ] `COORD_GAP_LEDGER.md` updated: gap 3 closed; ALL four COORD gaps now closed. Ledger notes the
      bridge is a waypoint per ADR-018 with the unify promotion trigger recorded.

## 2. Report-back

- Phase-1: confirm the write succeeded (gap demonstrated).
- Phase-2: the cross-agent denial assertion and the agreement-at-conflict assertion, verbatim —
  these are the real result.
- Backward compat: did any existing `agent_lib` test change? (Must be no.)
- Any place the two-records-must-agree invariant felt fragile during implementation — that fragility
  is the ADR-018 debt made concrete and worth noting for the future unify decision.

## 3. Out of scope (recorded, not built)

- Unifying the two ownership mechanisms into one authority (ADR-018 target; deferred until a
  promotion trigger fires).
- TTL / lease expiry, hierarchical path claims, cross-thread reservation handoff.
- Any live-model multi-agent run — COORD-02 is deterministic. With the control plane (COORD-01) and
  enforced reservations (COORD-02) both verified deterministically, a live multi-agent run becomes
  the natural next campaign, but it is not part of this spec.
