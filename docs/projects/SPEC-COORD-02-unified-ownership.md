# SPEC-COORD-02 — Unified Path Ownership (Single Atomic Authority + Reservation View)

**Status:** Draft for Codex (v3 — incorporates the atomicity + wiring review).
**Replaces:** the withdrawn bridge spec `SPEC-COORD-02-enforced-reservations.md` (mark it withdrawn, do not delete).
**Covers:** Ledger gap 3, via UNIFICATION with atomic acquisition. Closes the COORD ledger.
**Depends on:** SPEC-COORD-01 (ae377bc), ADR-018 (promoted to unify).
**Mode:** Deterministic, probe-first. No live model.
**Discipline:** Touches BOTH repos. `agent_lib` + ADR-018 + ADR_INDEX in `~/repos/ai_tools`. Probe in
`~/repos/computer_helper`. Separate commits. READ confirmed facts before coding.

---

## 0. Why this v3 exists

The v2 unify spec was directionally right but not safe to execute. Design review found:
1. **Acquisition is not atomic.** `acquire_patch_lease` does load→inspect→save with a bare `write_text`
   (programming.py 302–303, 354–364). Two processes can both read an empty store and both win. A single
   record makes conflict unrepresentable ONLY IF acquisition is atomic. The lock is therefore load-bearing
   to the unify justification, not an add-on.
2. **View and write runtime can be backed by different managers.** If the mailbox-view's `isolation_manager`
   and a worker runtime's manager differ (or one is absent), a reservation reports active/conflict without
   controlling that runtime's writes — reintroducing two-records, relocated. One record *type* is not enough;
   the coordinator and its workers must share one record *instance* (same manager).

Plus four API corrections and three doc-consistency fixes (§5, §6). All are adopted; none is pushed back on.

## 1. Confirmed facts (assert against these)

- `acquire_patch_lease(owner_id, paths)` persists `{path: {owner_id, status}}` to `_leases_path`, normalizes
  via `_normalize_rel_path`. `_save_json` is bare `write_text` — NOT atomic, NO lock.
- `release_patch_lease` currently returns ALL requested normalized paths as `status="released"` regardless of
  whether the caller actually held them (programming.py 366–374) — over-reports. The view needs the truthful set.
- `WorkspaceIsolationManager.__init__(state_root)` owns `_leases_path = state_root/"patch_leases.json"`.
- Lease record is thinner than `FileReservation` (`{owner_id, status}` vs `path, holder, thread_id, status,
  note, created_at, metadata`).
- **Direct `InMemoryMailbox` consumers (corrected count — THREE sites):** `examples/integration_mode.py:39`,
  `tests/test_integration_mode.py:37`, and the coordinator default (`coordination.py:234`). Plus
  `examples/mode_comparison.py` + `test_mode_comparison.py` use `reserve_paths`. Backward compat must hold for all.
- Current view semantics to preserve: `reserve_paths` → active, or conflict (diff holder, no mutation);
  `release_paths` → released only for paths actively held by the caller, skip others; re-reserve own → active.

## 2. Target architecture (ADR-018 promoted)

ONE atomic enforced authority (manager-backed mode). Reservation is a derived view. The "one authority"
guarantee is **conditional on manager-backed mode**; the no-manager fallback is legacy advisory-only (§2e).

### 2a. Atomic, cross-process-locked lease store (programming.py) — load-bearing
- Wrap acquire/release in a **cross-process lock**: a lockfile beside `_leases_path` (e.g.
  `patch_leases.lock`) held via `fcntl.flock` (LOCK_EX) for the full load→inspect→mutate→save critical
  section. Provide a portable acquisition with a timeout and stale-lock tolerance; document the `fcntl`
  POSIX assumption (workstation is Linux — acceptable; note Windows is unsupported for multi-process).
- Replace `_save_json`'s bare write with **atomic write-via-temp-rename**: write to `path.with_suffix(".tmp")`
  then `os.replace` onto the target (atomic on POSIX same-filesystem). The lock serializes writers; the
  atomic rename prevents torn reads.
- **New test (the gate for this issue):** concurrent acquisition — spawn 2+ threads/processes racing to acquire
  the SAME path; assert exactly one gets `active` and the rest derive `denied`. Without this test the atomicity
  claim is unverified.

### 2b. Lease record scope-aware + "denied is transient, not persisted" (programming.py)
- Persisted record becomes `{owner_id, status: "active"|"released", thread_id, note, created_at, metadata}`.
  **`status` is only ever `active` or `released` in the store.** `denied` is a transient *result* of an
  acquisition attempt, DERIVED from the current active owner — never written to disk. `PatchOwnership` returned
  on a failed acquire carries `status="denied"` but nothing persists it.
- `acquire_patch_lease` gains optional `thread_id="default"`, `note=""`, `metadata=None`; stamps `created_at`
  on first active acquisition. Defaults preserve every existing call site.
- **Create-or-preserve, not overwrite:** if the SAME owner reacquires a path they already hold active,
  PRESERVE existing `thread_id/note/created_at/metadata` — do not stomp them with defaults. This is what lets
  A's later `replace_text` (which reacquires the lease via the gate) keep A's reservation scope intact.
- **Truthful release:** `release_patch_lease` must return only the paths the caller actually held active and
  released. Either change its return to the real set, or add a method the view can use to learn it. The view's
  `release_paths` promise (return only genuinely-released) depends on this.
- Canonicalization: `_normalize_rel_path` is THE single canonical-path rule; the view (2c) normalizes
  identically. Reuse it; do not add a second rule.
- **Migration:** existing `_leases_path` files have records lacking the new fields. The reader MUST treat
  missing fields as defaults (thread_id="default", note="", `created_at=None`, metadata={}). A legacy
  `created_at` remains unknown: reads MUST NOT stamp or persist a synthetic timestamp. Only an acquisition
  operation (including a later same-owner reacquisition of a legacy record) may stamp `created_at`; a future
  TTL-like feature requiring guaranteed timestamps must introduce an explicit, locked migration. The
  `FileReservation` view must therefore allow `created_at: datetime | None`.
  New test: read a legacy-shaped record without crashing and assert its view has `created_at is None`.

### 2c. Reservation as a view over the lease (coordination.py)
`reserve_paths`/`release_paths`/`active_reservations` keep signatures and return `FileReservation`, deriving
from lease state:
- `reserve_paths(holder, paths, thread_id, note)` → per path `acquire_patch_lease(holder, [path],
  thread_id=, note=)`. Active → `FileReservation` from the record. Denied (derived) → `FileReservation(
  status="conflict", metadata={"current_holder": <active owner>})`. The conflict view is now backed by the
  same enforced denial that blocks the write.
- `release_paths(holder, paths)` → `release_patch_lease`, return `FileReservation(status="released")` only for
  the truthfully-released set (2b), skip others.
- `active_reservations(thread_id=None)` → read active leases, optional thread filter, return views sorted by path.

### 2d. Shared-manager construction seam (coordination.py) — the wiring fix
- Add a factory/seam so the coordinator-view AND every worker runtime in a team are constructed with the
  **same `WorkspaceIsolationManager` instance**. A reservation and the write it governs MUST consult one store.
- **New test:** build a team via the seam; assert the manager backing the mailbox-view is the SAME object
  backing each worker runtime; then assert a worker's denied write corresponds to a reservation conflict from
  the view (one authority, proven by shared instance, not by coincidence).

### 2e. Fallback is legacy advisory-only (scope the guarantee honestly)
- A mailbox with no isolation_manager keeps the legacy in-memory `_reservations` advisory behavior — UNCHANGED,
  for backward compat of the three direct-construction sites. Document explicitly: the "single authority /
  conflict-unrepresentable" guarantee holds ONLY in manager-backed mode. The fallback is a separate advisory
  authority by design and is not enforced. Do not claim global one-authority.

## 3. Probe-first (computer_helper)

### Phase 1 — demonstrate the pre-unify gap (REAL disk mutation)
Use a runtime whose `replace_text` actually writes to disk (COORD-01 fixture's replace does NOT edit disk —
do not reuse it for this). A reserves advisory-only (or enforcement not wired); B writes `shared.py`; assert
the FILE CONTENT changed. Record gap-3 confirmed.

### Phase 2 — unified enforcement (manager-backed)
1. A reserves `shared.py` via unified `reserve_paths` (manager-backed seam).
2. B's `replace_text` on `shared.py` DENIED `ownership_denied` AND file on disk UNCHANGED. (the result)
3. B's `reserve_paths(...["shared.py"])` → `status="conflict"`, `metadata["current_holder"]=="agent_a"` — same
   record that enforces the denial produces the conflict view.

### Required tests (the implementation gate)
- Phase 1 real-disk mutation; Phase 2 denial + file-unchanged.
- **Concurrent acquisition** (2a): 2+ racers, exactly one active.
- **Release/reacquire**: A reserves then releases → B reserves active → B write allowed (symmetric release: one release frees view + enforcement).
- **Same-owner reacquire preserves scope** (2b): A reserves with thread/note; A's replace_text reacquires; assert thread_id/note/created_at/metadata unchanged.
- **Canonical-path**: A reserves `shared.py`; B reserves `sub/../shared.py` → B conflict (one canonical path).
- **Legacy-record migration** (2b): read a `{owner_id,status}`-only lease without crashing; its reservation
  view has `created_at is None` (no timestamp is synthesized or persisted on read).
- **Shared-manager wiring** (2d): mailbox-view manager IS the worker-runtime manager (same instance); denial ⇔ conflict.
- **Backward compat**: no-manager mailbox behaves advisory-only; `mode_comparison`/`integration_mode` + their tests unchanged.

## 4. Done criteria
- [ ] ADR-018 (promoted) linked from ledger AND added to `ai_tools/ADR_INDEX.md`. Also add ADR-017 (missing).
- [ ] Atomic lock + temp-rename in lease store; concurrent-acquisition test passes.
- [ ] Lease record scope-aware; denied transient/not-persisted; create-or-preserve; truthful release.
- [ ] View derives from lease; signatures/return types unchanged; single canonical rule.
- [ ] Shared-manager seam; wiring test passes.
- [ ] All required tests (§3) pass.
- [ ] Existing `agent_lib` suite green — three direct-construction sites + reserve_paths consumers unchanged.
- [ ] compileall clean both repos; git diff --check clean both repos; library + probe commits separate.
- [ ] Withdrawn bridge spec marked WITHDRAWN with pointer (not deleted). Ledger: gap 3 stays OPEN until this lands, then closed with all four COORD gaps.

## 5. Adopted corrections (from review, for traceability)
- Atomic cross-process lock + concurrent test (2a). — blocking
- Shared-manager seam + wiring test (2d). — blocking
- Same-owner reacquire preserves scope metadata (2b).
- Truthful `release_patch_lease` result (2b).
- Denied = transient result, not persisted state (2b).
- "One authority" conditional on manager-backed mode; fallback is advisory-only (2e).

## 6. Doc-consistency (do these in the library commit)
- Mark `SPEC-COORD-02-enforced-reservations.md` WITHDRAWN at top, pointer to this file. Do not delete (trail).
- Add ADR-018 and ADR-017 to `ADR_INDEX.md`.
- Ledger keeps gap 3 OPEN until implementation completes (correct as-is).

## 7. Out of scope (recorded, not built)
- TTL/expiry, hierarchical paths, cross-thread handoff. Windows multi-process locking (POSIX fcntl only).
- Live-model multi-agent run — deterministic only here; it is the natural next campaign once COORD-02 lands.
