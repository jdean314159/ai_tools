# SPEC-COORD-00 — Deterministic Coordination Probe (Option B)

**Status:** Draft for Codex.
**Project location:** `~/repos/computer_helper` (sibling to `~/repos/ai_tools`).
**Consumes:** `agent_lib` via editable install (install.sh already validated).
**Mode:** Deterministic only. No live model. This is the SPEC-ASC-00 analog for the
coordination layer.
**Discipline:** READ `agent_lib/src/agent_lib/coordination.py` before writing probe code.
Assert against real behavior confirmed below, not assumed behavior.

---

## 0. Why this spec exists, and what it deliberately does NOT do

The original intent was a full-loop coordination probe: capability-based routing, enforced
permission isolation, and a coordinator-never-executes invariant. Reading `coordination.py`
established that **none of those three primitives exist** in `agent_lib`:

- `ExternalSessionCoordinator` is a messaging + advisory-reservation surface. It has no
  `route()`/`dispatch()` that selects an agent by capability. The caller names the recipient.
- `ExternalAgentSession` carries `agent_id`, `role`, `workspace`, `metadata` — no
  `allowed_tools` or permission field. Tool/command scoping lives in `WorkspacePolicy` /
  `ProgrammingToolRuntime` (the single-agent execution path) and is not wired to coordination.
- File reservations are explicitly advisory — `FileReservation` records a holder; nothing
  prevents another agent from writing a reserved path.

Therefore SPEC-COORD-00 probes **only what exists** and treats the three missing primitives as
documented gaps (§4). This is the ASC-consistent move: verify the real surface, let the probe's
inability to express routing/isolation become the forcing evidence for a future `agent_lib`
enhancement (SPEC-COORD-01), rather than building speculative machinery now.

---

## 1. Confirmed real behavior (assert against these)

From `agent_lib/src/agent_lib/coordination.py`:

- `InMemoryMailbox.send` auto-registers unknown sender and recipient as
  `ExternalAgentSession(role="unknown")`, then appends the message.
- `fetch_inbox(recipient, thread_id=None)` filters by recipient; if `thread_id` given, also
  filters by thread. Returns a list copy.
- `reserve_paths(holder, paths, thread_id, note)`: for each path, if an `active` reservation
  exists held by a *different* holder, returns a `FileReservation` with `status="conflict"` and
  `metadata={"current_holder": ...}` — it does NOT raise. Otherwise creates/overwrites an
  `active` reservation held by `holder`. Re-reserving a path you already hold returns `active`
  (idempotent).
- `release_paths(holder, paths)`: only releases paths currently `active` AND held by `holder`;
  silently skips others. Released reservations get `status="released"`.
- `active_reservations(thread_id=None)`: returns `active` reservations, optionally thread-filtered,
  sorted by path.
- `ExternalAgentTeam` has `mentor`, `workers`, optional `critic`, `scouts`; `.all_sessions`
  flattens them. `ExternalSessionCoordinator.register_team` registers every session in the mailbox.
- `FileReservation` fields: `path, holder, thread_id, status, note, created_at, metadata`.
- `MessageKind` is a `Literal`; read the exact allowed values from line 8 and use a valid one.

---

## 2. Project scaffold (`~/repos/computer_helper`)

Create:

```
~/repos/computer_helper/
  AGENTS.md                      # Codex instructions scoped to THIS repo
  pyproject.toml                 # depends on agent-lib, rag-lib (editable, already installed)
  install.sh                     # documents the bottom-up editable install (already run)
  probes/
    __init__.py
    coord_probe_00.py            # the deterministic probe
  tests/
    test_coord_probe_00.py       # pytest assertions
  runs/                          # probe output artifacts
```

`AGENTS.md` must state: changes land in `~/repos/computer_helper` only. If the probe surfaces an
`agent_lib` gap, that is a SEPARATE, explicitly-scoped change to `~/repos/ai_tools` with its own
ADR — never an incidental edit during probe work.

---

## 3. Probe scenario — three specialists, one coordinator

A deterministic fixture modeling the helper-agent shape WITHOUT the missing primitives. The
coordinator (here: the test harness, since `agent_lib` has no router) assigns tasks to named
specialists by a hand-written routing table. The probe verifies the **messaging and reservation**
behavior that supports such a design, and records where enforcement is absent.

Specialists (each an `ExternalAgentSession`):
- `fs_agent` — role `"filesystem"`, would hold file tools.
- `search_agent` — role `"retrieval"`, would hold a `rag_lib` retrieval tool.
- `calc_agent` — role `"compute"`, would hold a compute tool.

Coordinator: `coord` — role `"coordinator"`.

### Assertions (deterministic, no model)

**A. Routing by a declared table (caller-side, not library).**
Build a `dict[str, str]` mapping task-kind → agent_id. The harness routes three tasks
(`"read_config"→fs_agent`, `"lookup_doc"→search_agent`, `"sum_metrics"→calc_agent`) by sending
a `CoordinationMessage` from `coord` to the mapped recipient. Assert each specialist's inbox
contains exactly its task and no other. This verifies recipient-addressed delivery — the
mechanism a real router would sit on top of. **Document explicitly in the probe report: the
routing decision is made by the harness table, NOT by `agent_lib`. The library provides
addressing, not routing.**

**B. Thread isolation.**
Send two tasks to `fs_agent` on different `thread_id`s. Assert `fetch_inbox(fs_agent,
thread_id=X)` returns only thread X's message. Verifies thread-scoped delivery.

**C. Reservation conflict detection (advisory).**
`fs_agent` reserves `config.json`. `calc_agent` attempts to reserve `config.json`. Assert
`calc_agent`'s result has `status="conflict"` and `metadata["current_holder"] == "fs_agent"`,
and that NO exception was raised. Then assert that the conflict is **advisory only**: there is no
API that prevents `calc_agent` from proceeding to write — record this as the isolation gap (§4).

**D. Idempotent re-reservation and release.**
`fs_agent` re-reserves `config.json` → `status="active"` (not conflict). `fs_agent` releases it
→ `status="released"`. `calc_agent` now reserves `config.json` successfully → `active`. Verifies
the release/reacquire cycle.

**E. Coordinator does not execute (trivially true).**
Assert `ExternalSessionCoordinator` exposes no execution method (no `run`, `execute`, `invoke`
tool-calling surface). Document that this invariant holds **by absence of capability**, not by a
designed guard — the coordinator can't execute because it has no execution path, which is a
weaker guarantee than an enforced never-execute rule. Record as gap (§4).

---

## 4. Gap ledger (the real deliverable)

The probe's primary output is a `COORD_GAP_LEDGER.md` in `runs/` naming each missing primitive
the full-loop design needs but `agent_lib` does not provide:

1. **No capability-based routing.** Routing is caller-supplied. A real coordinator that selects
   an agent by required tool/capability does not exist. Forcing run for SPEC-COORD-01: a scenario
   where the correct agent must be chosen from capability metadata, not a hardcoded table.
2. **No per-agent tool permissions.** `ExternalAgentSession` has no `allowed_tools`. Cannot assert
   "wrong agent COULDN'T have executed" because there is no permission to violate. Forcing run:
   an agent attempting a tool outside its grant and being denied.
3. **Reservations are advisory, not enforced.** Conflict is reported; writing is not prevented.
   Forcing run: two agents writing the same reserved path and the harness needing enforcement.
4. **Coordinator-never-executes is by-absence, not by-design.** No guard; just no capability.
   Forcing run: a coordinator that DOES have tool access and must be prevented from direct use.

Each gap entry must state: the missing primitive, why the probe can't assert the full-loop
property, and the concrete run that would justify building it. **Do not build any of these now.**

---

## 5. Done criteria

- [ ] `~/repos/computer_helper` scaffold created with its own `AGENTS.md`.
- [ ] `coord_probe_00.py` imports `agent_lib.coordination` via the editable install (no
      `PYTHONPATH` manipulation).
- [ ] `pytest tests/test_coord_probe_00.py` passes assertions A–E.
- [ ] `COORD_GAP_LEDGER.md` written with all four gaps and their forcing runs.
- [ ] `python -m compileall -q probes tests` passes.
- [ ] `git diff --check` clean (in the computer_helper repo).
- [ ] No file under `~/repos/ai_tools` modified.

## 6. Report-back

- A–E pass/fail.
- Confirm the gap ledger's four entries against the code (did any primitive actually exist that
  this spec assumed absent?).
- Any behavior of the existing surface that surprised the probe (e.g. auto-registration side
  effects, reservation overwrite semantics) — these are candidate findings for the ledger.

## 7. What COORD-00 explicitly does not decide

Whether to build the missing primitives in `agent_lib` (SPEC-COORD-01, Option A) or build the
helper on external coordination (`mcp_agent_mail`, Option C) is deferred until the ledger exists.
The ledger is the input to that decision, not a commitment to Option A.
