# SPEC-LIVE-00 — Live Multi-Agent Run (probe-first, observe-only)

**Status:** Ready to implement as revision-and-rebase (v8 — sixth review: conformance, evidence provenance, pinned policy).
**Covers:** First live (model-in-loop) exercise of the COORD control plane through a probe-local orchestrator.
Opens the LIVE campaign.
**Depends on:** SPEC-COORD-01 (4a5c671), SPEC-COORD-02 / ADR-018 (unified ownership). All four COORD gaps closed.
**Mode:** LIVE with deterministic REPLAY. `--live` drives a real local model and records a normalized event
transcript; `--replay` (test default) deterministically re-executes recorded events — no GPU, no model.
**Discipline:** Probe lands in `~/repos/computer_helper` ONLY. This run adds NOTHING to `agent_lib`. Any
surfaced library gap becomes a SEPARATE, explicitly scoped `~/repos/ai_tools` change with its own ADR (per
`computer_helper/AGENTS.md`).
**Governing rule:** Gate on the control plane's RESPONSE to model output, never on the model's correctness.
Deterministic adversarial fixtures — NOT live model fallibility — provide gate coverage.
**Conformance (revision-and-rebase, not greenfield):** v8 is canonical and SUPERSEDES the existing
`codex/live-00` branch, which is NON-CONFORMING (four fixtures, no FX-CONTENTION; no targeted-agent route so
`fs_b` is unreachable; deadlock weaker than predicate D; no semantic-normalization or fresh-state isolation
tests). That branch must be UPDATED to v8, not merged as-is: start from its replay harness, add targeted routing
(§3.1/§3.3) + FX-CONTENTION (§6), strengthen the deadlock classifier to predicate D (§3.1) and the replay tests
to §8.2. The updated probe and this spec MUST land as coordinated commits in their respective repositories, each
cross-referencing the other commit; neither change is complete without the other. This prevents the earlier drift,
where the spec advanced while the probe sat frozen on the unmerged branch.
**Implementation reference:** the v8-conforming probe is `computer_helper` commit `7cb5192`
(`feat(probe): conform LIVE-00 harness to v8`), whose commit message references this spec commit (`14ac320`).
**Live confirmation:** `computer_helper` commit `7e40b36` records a fresh `qwen3:8b` v8 run. The authoritative
done-check became satisfied at step 4; the coordinator issued four further `replace_text` routes, and the run
ended at `step_cap` on step 12. Finding 1 is therefore CONFIRMED in-tree.

---

## 0. Revision history

### v8 — sixth review (this revision)

Spec was sound but had drifted ahead of the only implementation (the unmerged `codex/live-00` branch, pre-v7).
Three corrections, no mechanics change:
1. **Finding 1 was claimed CONFIRMED on out-of-tree evidence.** Demoted to OBSERVED on `codex/live-00` (pre-v7),
   pending re-confirmation on a v8-conforming run; the transcript/ledger live on the unmerged branch, not
   `master` (§4).
2. **Conformance stated.** v8 SUPERSEDES `codex/live-00`, which is non-conforming; it must be updated to spec,
   not merged as-is. Revision-and-rebase from its replay harness; the updated probe and this spec land as
   coordinated, cross-referenced commits in their respective repositories (header Conformance note).
3. **Seed policy pinned.** `enforce_patch_ownership=True`, `approval_mode="auto"`, writable `config.toml` set
   explicitly at construction with a test asserting them, so I3/predicate D do not silently depend on library
   defaults (§2).

### v7 — fifth review

Two invariant-boundary corrections; v6 mechanics (predicate D, malformed-lease, semantic replay) confirmed good.
1. **I2/I4 overlap on unknown tools.** I2 said "any tool outside capabilities → `tool_not_granted`," but an
   unrecognized tool name is `unknown_tool` (I4), caught by the probe's tool-set guard before dispatch. Narrowed
   I2 to a RECOGNIZED-but-ungranted tool (the runtime-denial case, e.g. FX-WORKER-GRANT's
   `search_agent`→`replace_text`); unrecognized names stay with I4.
2. **"Absolutize paths" was backwards.** A fresh `runs_root` yields different absolute paths, so absolutizing
   makes comparison worse. §8.2 now says relativize to the workspace root, replace the `runs_root` prefix with a
   stable token, or omit paths.

### v6 — fourth review

Three more contract defects, two of them the SAME self-contradiction class the v5 consolidation was meant to end
— which means that consolidation was applied to a named list (I1–I6) rather than exhaustively. Now swept:
1. **Deadlock predicate drifted** between §3.1 ("every subsequent fs dispatch denied" — vacuously true with no
   contender) and FX-CONTENTION/code ("one denial"). Promoted to single-source **predicate D** (§3.1) requiring
   ≥1 non-holder `ownership_denied` (the non-vacuous guard) AND no permitted non-holder write AND done never
   satisfied AND `step_cap`; §4 and §6 now reference D, do not restate. This is the seventh invariant; it should
   have been consolidated with I1–I6.
2. **Malformed call cannot hold a lease.** §2 listed "a malformed call" as a contention trigger, but malformed
   output is skipped without dispatch (§3.4) and a lease is acquired only inside a permitted `replace_text`
   dispatch. Removed; the sole non-progress holder case is a `replaced=False` no-op (§2).
3. **Replay was not byte-deterministic.** Lease snapshots embed `created_at`; fresh replay yields new timestamps.
   I6 reworded as SEMANTIC determinism; §8.2 now requires comparison on the semantic projection with timestamps
   normalized/omitted, not a raw byte-diff.
Minor: §2 now says the first PERMITTED `replace_text` dispatch acquires the lease (a no-op acquires it too), not
"the first worker to write."

### v5 — third review

Third Codex review of the v4 worker-addressing change. Architecture accepted; three blocking fixes + two
corrections, all adopted:
1. **Contention assertion was self-contradictory.** FX-CONTENTION has the holder no-op and the non-holder denied
   — zero disk writes — but §5 asserted "exactly one writes." Reframed the invariant around lease OWNERSHIP, not
   substitution: exactly one holder, non-holder `denied`, a successful `replaced=True` only if the holder's `old`
   matched (§5, §6).
2. **Done-check before retrieval was undefined.** `_done()` is False whenever `canonical is None`
   (`live_probe_00.py:93`); FX-CONTENTION performs no `retrieve`, so done stays unsatisfied throughout. Stated
   explicitly (§2, §6).
3. **Replay isolation under-specified.** Provenance fingerprints seed files only; `_seed()` never clears
   `state_root`, so a reused `runs_root` leaks lease state. Each replay/fixture MUST use a fresh unique
   `runs_root` with an empty `state_root` (§8.2).
Corrections: §7 git-clean gate scoped to `-- agent_lib` (this spec doc is itself a new file under
`~/repos/ai_tools/docs`); §3.3 "never targets" reworded as intended/default prompt behavior, since the parser
accepts a targeted route in live mode.

**Single-source consolidation (root-cause fix for the recurring self-contradiction class).** The contention
contradiction existed because the same invariant was stated in full in both §5 and §6 and the two drifted. The
harness invariants are now stated ONCE as I1–I6 at the top of §3; §5 references them conditionally and §6
fixtures supply only construction plus the invariant id. No invariant is restated in more than one place, which
removes the surface that produced the v3/v4/v5 contradictions. Section numbers unchanged.

### v4 — worker-addressing for contention

The live run reached the success path and surfaced the termination-contract gap (Finding 1, §4). Implementation
then exposed a latent oversight from v1: §3.3 made the route schema capability-only and `route_by_capability` is
first-match, so `replace_text` always resolves to `fs_a` and nothing can address `fs_b`. Consequence: FX-CONTENTION
(gate 3) AND the probe's own deadlock classifier (`bool(denied_fs)`) are both unreachable — the second-writer
denial that `denied` requires can never occur. Fix (Option A, probe-local): the route schema gains an OPTIONAL
`agent` field (§3.3); targeted selection picks the named session iff it declares the capability (§3.1). The
default capability-only path and `route_by_capability` are unchanged, so the live model's behavior and every live
finding are untouched — the field exists for fixtures to force contention. The need for it is itself recorded as
Observation 2 (§4): the coordination layer has no worker-addressing.

### v3 — second review

The second Codex review accepted the v2 architecture (probe-local scheduler, route schema, adversarial fixtures,
conditional live assertions) and found one contradiction plus two clarifications. All adopted:

1. **FX-COORD-TOOL contradiction (resolved, option 1).** v2's fixture asserted a coordinator `kind=tool` payload
   returns `tool_not_granted`, but §3.1/§3.3 classify every non-route coordinator payload as malformed with NO
   dispatch — so it can only produce `malformed_route`, never reaching a runtime. The coordinator's route schema
   intentionally cannot express a tool call. Adopted the tighter behavior: coordinator `kind=tool` is
   `malformed_route`/skip; the fixture now asserts zero coordinator side effect, not `tool_not_granted` (§6).
   The `allowed_tools=[]` coordinator-deny enforcement is already proven by `coord_probe_01` stage 3; LIVE-00
   proves the coordinator has no execution PATH in the live loop, which is the live-relevant property.
2. **Lease-acquisition inference specified.** The worker runtime exposes no successful-acquisition marker in
   `ToolResult.meta` (only the deny path sets `meta["error"]="ownership_denied"`, programming.py ~509). The probe
   infers `lease_outcome` by reading the shared manager before/after dispatch (§3.5), via
   `WorkspaceIsolationManager.patch_lease(path)` / `active_patch_owners()` (programming.py ~448, ~394).
3. **Replay-determinism provenance.** Replay is deterministic relative to a versioned seeded workspace AND
   deterministic tool handlers, not `raw_response` alone. The transcript now carries a provenance header
   (schema/fixture version, workspace fingerprint, tool-handler id) that `--replay` validates before executing
   (§8.1).

### v2 — first review

v1 was directionally right but assumed a multi-agent execution loop `agent_lib` does not provide. Design review
(Codex) found four blocking gaps, all confirmed against the code and all adopted:

1. **No orchestrator in the seam.** `LLMActionPlanner` drives ONE `AgentRuntime`/`ToolRuntime`; no
   coordinator→worker routing, no target-agent field, no mailbox dispatch, no team turn scheduler.
   `RoleEngineSet` supports only `planner/executor/critic/fallback` — NOT the named sessions in the task.
   (`agent_lib/src/agent_lib/llm_engines_adapter.py:14`.)
2. **Action schema cannot express a route.** Actions are `kind` ∈ {tool, final, message} with
   `tool_name`/`arguments`; there is no "route capability X to agent Y." (`llm_engines_adapter.py:84`.)
3. **Several v1 hard gates required model behavior that cannot be guaranteed** (two workers writing the same
   path; a coordinator attempting a tool; malformed/unknown-tool/unroutable output). A live model may emit none.
4. **The claimed ASC `arguments.tool_name` normalization does not exist** on this path — `action_from_payload`
   reads only top-level `tool_name` or `name`. (`llm_engines_adapter.py:84`.)

Resolution, adopted in full: the multi-agent loop is **probe-local machinery, explicitly specified** (§3); the
existing single-agent seam is used ONLY for a single agent's single-step planning (§3.2); gate coverage comes
from **deterministic adversarial replay fixtures** (§6), with live assertions made **conditional over observed
events** (§5); the nested-tool-name form is **classified malformed by the probe** (§3.4), not assumed normalized.

## 1. Confirmed facts (assert against these; do not reinvent)

- **Control-plane primitives `agent_lib` DOES provide:** `ExternalAgentSession(agent_id, role,
  capabilities=[...])`; `ExternalAgentTeam(project_id, mentor, workers)`;
  `route_by_capability(team, capability)` → first declaring session or `None` (first-match only);
  `build_managed_coordination(team, tools, policy, root=, state_root=)` → `ManagedCoordination(coordinator,
  worker_runtimes)` with one shared `WorkspaceIsolationManager`; `WorkspacePolicy(root, writable_paths,
  allowed_tools)` (`None`=unrestricted, `[]`=deny-all, list=grant); `EnforcingToolRuntime` checking tool
  identity BEFORE write-path policy. Denials: `result.success is False`,
  `result.meta["error"]` ∈ {`tool_not_granted`, `ownership_denied`}. Conflicts: `status="conflict"`,
  `metadata["current_holder"]`.
- **Lease-state accessors (for §3.5 acquisition inference):** `WorkspaceIsolationManager.patch_lease(path)` →
  `{owner_id, status, thread_id, note, created_at, metadata}` or `None` (programming.py ~448);
  `active_patch_owners()` → the full `{path: record}` map (programming.py ~394). The runtime success path writes
  NO lease marker into `ToolResult.meta`; only the deny path sets `meta["error"]="ownership_denied"`
  (programming.py ~509). Acquisition is observed via these accessors, never read off the result.
- **What `agent_lib` does NOT provide (must be probe-local):** any team turn loop, any coordinator-to-worker
  dispatch, any mapping from a model response to a chosen worker, any route-decision action kind, any
  per-session engine binding beyond the 4 fixed roles.
- **Single-agent seam (use for §3.2 only):** `RoleEngineSet`(planner/executor/critic/fallback);
  `LLMActionPlanner.plan(context)` = one `engines.invoke(role,...)` → `extract_json_object` →
  `action_from_payload` → ONE `AgentAction`. `action_from_payload` reads top-level `tool_name`/`name` only.
- **Default model:** `qwen3:8b`. Qwen thinking-disable triple-block applies for Ollama/llama.cpp backends.

## 2. The task (config-reconciliation)

Requires two distinct capabilities, creates lease contention only on the failure path, harness-owned done-check.

**Goal:** make `config.toml`'s `version` equal the canonical value, which lives in a separate retrieval source.
Requires retrieve → read → write.

**Seed workspace** (temp dir, no real OS reach — same containment as `coord_probe_02`):
- `config.toml` with stale `version = "0.9.0"`.
- `canonical.md` with the true value `1.2.0`.

**Required policy (pin explicitly; do NOT rely on library defaults — the lease invariant I3 depends on these):**
the `WorkspacePolicy`/managed coordination is built with `enforce_patch_ownership=True` (else leases are advisory
and I3/predicate D do not hold), `approval_mode="auto"` (no human-gate stall in the loop), and `config.toml`
listed in `writable_paths` (else every write is denied for the wrong reason). A future `agent_lib` default change
must not silently weaken these — the probe sets them at construction and a test asserts them.

**Agents:** `coordinator` (`allowed_tools=[]`); `search_agent` (`["retrieve"]`); `fs_a`, `fs_b`
(`["read_file","replace_text"]` — deliberate overlap, see §2.1).

**Tools (real, on disk, lease-gated through the managed runtimes):**
- `retrieve(query)` → canonical value from `canonical.md`.
- `read_file(path)` → file contents.
- `replace_text(path, old, new)` → MUST mutate disk AND MUST return whether a substitution actually occurred
  (`{"replaced": bool}` or equivalent). A no-match call returns `replaced=False`; the probe records that as a
  distinct stale/no-op outcome, NEVER conflated with a lease denial or a real edit. (Do NOT reuse the COORD-01
  fixture whose `replace_text` neither touches disk nor reports a substitution.)

**Lease protocol (stated, to remove the ambiguity review flagged):** workers have NO release action in scope;
`invoke()` acquires on a permitted `replace_text` dispatch and does not auto-release (programming.py ~508).
Therefore the FIRST permitted `replace_text` dispatch acquires the lease and holds it for the remainder of the
run — a `replaced=False` no-op acquires it just the same as a successful write, because acquisition happens
inside the runtime dispatch before the substitution is attempted. In the happy path this is harmless: a
successful real substitution satisfies the done-check and the run terminates before any second write. Contention
arises ONLY when the holder acquired the lease but did NOT satisfy done (a `replaced=False` no-op — the holder's
`old` did not match) and the coordinator then dispatches the other fs worker — that worker is `ownership_denied`.
A malformed worker payload is skipped WITHOUT dispatch (§3.4) so it never acquires a lease and cannot be the
holder. Lease release is explicitly out of scope for this probe (§7).

**Done-check (harness-owned, deterministic, authoritative):** parsed `version` in `config.toml` equals the
value `retrieve` returned this run. Until a successful `retrieve` establishes that value, `canonical` is unset
and the check is UNSATISFIED by definition (`_done()` is False whenever `canonical is None`,
`live_probe_00.py:93`). The coordinator may *signal* completion, but the harness check is authoritative; a
coordinator "done" with an unsatisfied check is recorded as an overclaim and the run continues.

**Already-updated write:** if `config.toml` already holds the canonical value, any further `replace_text` with
the stale `old` returns `replaced=False` (no-op), recorded as stale; it does not error and does not re-satisfy
or un-satisfy the done-check.

**Step cap:** 12. A "step" = ONE model invocation (coordinator OR worker). The cap counts total invocations.

### 2.1 Why the two interchangeable fs workers are not artificial

A coordinator decomposing "read then write" across identical filesystem workers is exactly the condition the
lease exists to make safe. The overlap is the forcing condition, constructed as `coord_probe_02` constructed its
phase-2 contention.

## 3. Probe-local orchestrator (explicitly specified machinery)

This is the harness under test's *driver*. It is probe-only and adds nothing to `agent_lib`. Building it is
itself a finding (§4).

**Harness invariants (single source — referenced by §5 live assertions and §6 fixtures; do not restate
elsewhere):**
- **I1 — Coordinator executes nothing.** The coordinator's output is only ever a route decision or done-signal;
  it is never handed to a runtime, so it has no execution path. Any tool-shaped coordinator payload is
  `malformed_route` with zero side effect.
- **I2 — Workers cannot exceed their grant.** A RECOGNIZED tool (`retrieve`/`read_file`/`replace_text`) called
  by a worker whose session `capabilities` do not grant it is `tool_not_granted`, denied by the runtime during
  dispatch; the tool does not run. (An UNrecognized tool name is `unknown_tool` per I4, caught by the probe's
  tool-set guard BEFORE dispatch — that case is I4's, not I2's. FX-WORKER-GRANT exercises I2 with
  `search_agent`→`replace_text`: a real tool the session lacks.)
- **I3 — Lease ownership on `config.toml`.** At most one worker holds the lease; a non-holder write is
  `ownership_denied`. The invariant is ownership, not mutation: a substitution (`replaced=True`) occurs only if
  the holder's `old` actually matched, and the file never reflects a denied worker's write.
- **I4 — Bad output is recorded, never raised.** Every unparseable, unknown-tool, nested-tool-name (§3.4),
  unroutable, or unknown-agent output yields its deterministic recorded outcome (§8 enum); an exception is never
  propagated.
- **I5 — Bounded termination.** The run ends at `done` (authoritative `_done()` satisfied, surfaced via a
  coordinator done-signal) or at the 12-invocation `step_cap`; it never loops unbounded.
- **I6 — Deterministic, isolated replay.** Given matching provenance (§8.1) and a fresh `runs_root` (§8.2),
  replay re-executes recorded events to identical harness *decisions and classifications* with no model.
  Determinism is SEMANTIC, not byte-level: lease snapshots embed `created_at` (and other wall-clock/path fields)
  that differ on every fresh run, so replay comparison MUST compare semantic fields (`owner_id`, `status`,
  `lease_outcome`, `parse_outcome`, `done_check`, `termination_reason`, predicate D) and normalize or omit
  timestamps and absolute paths. See §8.2.

### 3.1 Scheduler state machine

Strict coordinator-driven alternation:

1. **Coordinator turn.** Invoke the coordinator engine with current team/workspace state. Parse a **route
   decision** against the probe schema (§3.3): `{"route": {"capability": str}}`, the targeted form
   `{"route": {"capability": str, "agent": str}}`, or `{"done": true}`.
   - Capability only → `route_by_capability(team, cap)` selects the first session with the capability (unchanged).
   - Targeted (`agent` present) → select that named session iff it exists AND declares `capability`; if the named
     agent is absent or lacks the capability, record `unknown_agent`, NO worker runs, control returns to the
     coordinator. (Targeting exists so fixtures can dispatch a second writer; the live model uses capability-only.)
   - Unroutable (no session has the capability) or malformed route → record outcome, NO worker runs, control
     returns to the coordinator. This consumes a step.
   - `{"done": true}` → run the authoritative done-check. Satisfied → terminate `done`. Unsatisfied → record
     `overclaimed_done`, continue.
2. **Worker turn.** Invoke the chosen worker engine; parse via the single-agent seam (§3.2) into an
   `AgentAction`.
   - `kind=tool` → dispatch through THAT worker's `worker_runtimes[id]` (enforces `allowed_tools` + lease).
     Record tool_result + lease_outcome.
   - malformed JSON / unknown `kind` / unknown tool / nested-tool-name (§3.4) → record parse_outcome, NO
     dispatch, return to coordinator.
   - After a worker turn, control returns to the coordinator.
3. **Termination.** `done` (check satisfied) OR `step_cap` (12 invocations reached). Post-hoc, the ledger
   classifies a `step_cap` run as **`deadlock` (predicate D — single source; §4 and §6 reference D, do not
   restate)** iff ALL of: (a) a worker actively holds the `config.toml` lease at cap; (b) at least one NON-HOLDER
   `replace_text` dispatch was `ownership_denied`; (c) no non-holder `replace_text` after acquisition was
   permitted (every later non-holder write denied); (d) the done-check was never satisfied. Clause (b) is the
   non-vacuous guard: it prevents a lone stalled holder with no contender — which makes (c) vacuously true — from
   being mislabeled `deadlock`. (Under the no-release protocol (§2), (c) is automatically satisfied whenever (a)
   holds; it is stated explicitly so the classifier remains correct if release is ever added.)

### 3.2 Per-session model binding

Each named session is driven for its SINGLE step by `engines.invoke(role="planner", ...)` (or a thin probe
wrapper) — one engine instance per session, all `qwen3:8b` in the default run. The 4 fixed `RoleEngineSet`
roles are NOT extended; the probe holds a `dict[agent_id -> engine]` itself. Worker steps reuse
`extract_json_object` + `action_from_payload` verbatim. The coordinator step does NOT use `action_from_payload`
(its output is a route decision, not an `AgentAction`); it uses `extract_json_object` + the §3.3 schema.

### 3.3 Probe-local route-decision schema

The coordinator emits, and the probe parses, exactly:
`{"route": {"capability": "<str>"}}`, the targeted form `{"route": {"capability": "<str>", "agent": "<str>"}}`,
or `{"done": true}`. The optional `agent` selects a specific session among capability-equal workers (§3.1); it
exists so fixtures can dispatch a second writer. The live coordinator prompt does not mention targeting, so the
model is not expected to emit `agent` — but the parser accepts it if present (live mode does not reject targeted
routes); this is intended/default prompt behavior, not a guarantee.
Anything else — missing keys, unknown capability type, non-JSON, OR a `kind=tool`/`message`/`final` payload (the
coordinator schema CANNOT express a tool call) — is a `malformed_route` per §3.1: recorded, NO dispatch, control
returns to the coordinator. A targeted route naming an absent/incapable agent is `unknown_agent` (§3.1). This
schema is PROBE-LOCAL; both its lack of a worker-addressing primitive in `route_by_capability` (Observation 2,
§4) and the absence of a library route-decision contract are recorded `agent_lib` gaps.

### 3.4 Nested-tool-name handling

A worker payload of the form `{"kind":"tool","arguments":{"tool_name":...}}` (top-level name empty, name nested
under arguments) is **classified malformed by the probe** and skipped/recorded. The probe does NOT normalize it
and does NOT modify `action_from_payload`. Whether `agent_lib` should normalize this form is a recorded
candidate gap requiring a separate ADR — NOT authorized here.

### 3.5 Lease-outcome inference (acquisition is read from the manager, not the result)

For a worker write dispatch on path `P` by worker `W`, the probe records `lease_outcome` as follows, using the
shared manager (§1 accessors):
- Snapshot `before = manager.patch_lease(P)` immediately BEFORE dispatch.
- `denied` ⟺ the `ToolResult` has `meta["error"] == "ownership_denied"`.
- `acquired` ⟺ dispatch did not deny AND `after = manager.patch_lease(P)` reports `after["owner_id"] == W` and
  `after["status"] == "active"`. Tag it `fresh` if `before` was absent/not-active-for-W, else `reacquire`
  (same-owner reacquisition preserves prior scope per programming.py acquire semantics).
- `n/a` for non-write tools (`retrieve`, `read_file`).
`released` is unused in this probe (no worker release action, §2 lease protocol). The before/after snapshots are
themselves recorded in the event (§8) so replay can assert the same classification without a live manager.

## 4. Soft observations (the LIVE gap ledger this run produces)

Recorded, ranked by named failing condition (forcing function), NOT acted on here.

- **Termination / budget contract (PREDICTED #3 — CONFIRMED, Finding 1).** A fresh v8 `qwen3:8b` run recorded in
  `computer_helper` commit `7e40b36` retrieved the canonical value at step 2 and made the authoritative `_done()`
  check satisfiable at step 4. The coordinator then issued four further `replace_text` routes; the run ended only
  at `step_cap` on step 12. `termination="done"` is set solely when the coordinator volunteers `{"done":true}`
  and `_done()` validates it; no autonomous predicate-driven stop exists. The transcript, results, and ledger are
  committed under `runs/live_00_v8_20260624/`. The fix (predicate drives termination; model `done` is an early-exit
  hint) belongs in SPEC-LIVE-01, likely an `agent_lib` ADR. Secondary, subordinate: coordinator context omitted
  the config contents / an explicit done flag (legibility) — would reduce frequency, cannot remove the dependency.
- **Worker-addressing absent (Observation 2).** `route_by_capability` is first-match-only and the route schema
  names only a capability, so among capability-equal workers only `fs_a` is selectable. A coordinator cannot
  distribute writes across interchangeable workers; multi-worker contention cannot arise through normal
  coordination and had to be forced via the probe-local `agent` field (§3.3). Worker-addressing is missing from
  the coordination layer. Feeds SPEC-LIVE-01.
- **Lease lifecycle under failure (PREDICTED #2).** Reachable only via the targeted route (above): a holder that
  fails to satisfy done while a non-holder is denied satisfies predicate D (§3.1). No TTL / owner-death
  reclaim / release-on-failure exists.
- **Malformed-output rate.** Counts by class: malformed_json, unknown_kind, unknown_tool, nested_tool_name,
  unroutable, unknown_agent, overclaimed_done. The nested-tool-name count motivates the §3.4 candidate gap.
- **Orchestration primitives the probe had to supply locally.** The §3 scheduler, the §3.3 route-decision
  contract (now including worker-addressing), the per-session engine binding, the coordinator/worker turn loop —
  none exist in `agent_lib`. The richest gap; primary driver of SPEC-LIVE-01.
- **Routing quality.** Coordinator routes to a missing/wrong capability; first-match cases where first-match is
  wrong.
- **Result acceptance.** Who validated a worker result before the coordinator accepted it? Proxy for unforced
  ASC gap #4 (typed critic contract).

## 5. Live assertions (conditional over observed events)

In `--live`, the harness invariants **I1–I6 (§3)** are asserted CONDITIONALLY: each must hold whenever its
triggering event is observed in the run, but the run does NOT require the event to occur. (E.g. a live `qwen3:8b`
coordinator may never emit a tool-shaped payload, so I1's trigger may not fire; if it does, I1 must hold.)

Live coverage is best-effort and proves nothing on its own. Deterministic GATE coverage of every invariant is
§6.

## 6. Hard gates — deterministic adversarial replay fixtures (the implementation gate)

Hand-authored normalized transcripts, committed, replayed with NO model, each in a fresh `runs_root` (§8.2). Each
fixture FORCES a named invariant from §3 that the live run might not trigger; the fixture supplies the
construction, the invariant supplies the assertion (do not restate it here). `--replay` over these MUST pass:

- **FX-COORD-TOOL → forces I1.** Construction: a coordinator response carrying `kind=tool`. (The `allowed_tools=[]`
  deny enforcement itself is already covered by `coord_probe_01` stage 3 and is NOT re-proven here.)
- **FX-WORKER-GRANT → forces I2.** Construction: `search_agent` emits `replace_text`.
- **FX-CONTENTION → forces I3 and the `deadlock` classification.** Construction: NO `retrieve` (so `canonical`
  stays `None` and `_done()` is unsatisfied throughout, per §2); `fs_a` takes the lease via a `replaced=False`
  no-op on a capability-only `replace_text` route; a TARGETED route
  `{"route":{"capability":"replace_text","agent":"fs_b"}}` then dispatches `fs_b` to the same path (denied per
  I3). The construction satisfies predicate D (§3.1): holder present, fs_b's denial is the required non-holder
  `ownership_denied`, no permitted non-holder write, done unsatisfied, run to `step_cap`. The targeted
  route is the only way to reach a second writer (§3.1/§3.3, Observation 2).
- **FX-MALFORMED → forces I4.** Construction: one each of non-JSON, unknown-tool, nested-tool-name (§3.4), and an
  unroutable capability.
- **FX-HAPPY → forces I5 and I6.** Construction: coordinator routes `retrieve`→`search_agent`,
  `read_file`→`fs_a`, `replace_text`→`fs_a` (`replaced=True`) → `_done()` satisfied → terminate `done`.

Replay = deterministic re-execution of recorded normalized events against the freshly seeded workspace (I6). It
is NOT a promise that arbitrary live output covers every invariant.

## 7. Done criteria

- [ ] `probes/live_probe_00.py` with probe-local orchestrator (§3), `--live`/`--replay`/`--runs-root`.
- [ ] Normalized event schema (§8) emitted by `--live`, consumed deterministically by `--replay`; transcript
      carries the §8.1 provenance header and `--replay` refuses on `schema_version`/`workspace_fingerprint`/
      `tool_handler_id` mismatch.
- [ ] `replace_text` returns `replaced: bool`; worker write events record `lease_before`/`lease_after` snapshots
      and the §3.5 `lease_outcome` classification.
- [ ] Five adversarial fixtures (§6) committed; `tests/test_live_probe_00.py` replays them with NO model/GPU and
      asserts every denial/loop/happy path. FX-COORD-TOOL asserts `malformed_route` + zero side effect.
- [ ] One `--live` run on the workstation (`qwen3:8b`); `LIVE_GAP_LEDGER.md` written with §4 observations ranked
      by named failing condition.
- [ ] `live_probe_00_results.json` records gate outcomes + observation counts by class.
- [ ] `agent_lib` untouched: `git -C ~/repos/ai_tools diff --exit-code -- agent_lib` is clean (scoped to
      `agent_lib`, since this spec doc is itself a new file under `~/repos/ai_tools/docs`); probe commit in
      `computer_helper` only;
      `action_from_payload` and `RoleEngineSet` unmodified.
- [ ] compileall clean; `git diff --check` clean.

## 8. Normalized event schema (probe-local, recorded per step)

Per step, record: `step`, `actor` (`coordinator`|worker id), `raw_response`, `parse_outcome`. The
`parse_outcome` enum is context-split:
- coordinator turn: `ok_route` | `done_signal` | `malformed_route` (missing keys, non-JSON, or a
  `kind=tool`/`message`/`final` payload) | `unroutable` (well-formed route, but no session declares the
  capability) | `unknown_agent` (targeted route naming an absent/incapable agent) | `overclaimed_done`
  (done-signal with an unsatisfied harness check).
- worker turn: `ok` | `malformed_json` | `unknown_kind` | `unknown_tool` | `nested_tool_name`.

Plus: `proposed_route` (capability|null), `chosen_session` (id|null), `dispatched_call` ({tool, arguments}|null),
`tool_result` ({success, error}|null), `lease_before`/`lease_after` (the §3.5 `patch_lease(P)` snapshots|null),
`lease_outcome` (`acquired_fresh`|`acquired_reacquire`|`denied`|`n/a`), `replaced` (bool|null, for replace_text),
`done_check` (`satisfied`|`unsatisfied`|`n/a`), `termination_reason` (null until end: `done`|`step_cap`, with
post-hoc `deadlock` flag).

### 8.1 Provenance header and replay validation

Replay is deterministic relative to a VERSIONED seeded workspace and deterministic tool handlers — NOT
`raw_response` alone. The transcript carries a header:
- `schema_version` (this event schema), `fixture_version` (for hand-authored fixtures),
- `workspace_fingerprint` — sha256 over the sorted seed file contents (`config.toml`, `canonical.md`) OR the
  inline seed contents themselves,
- `tool_handler_id` — an id/version for the deterministic `retrieve`/`read_file`/`replace_text` handlers,
- live provenance (informational, not replayed): `model_id`, `temperature`, `max_tokens`, any seed.

`--replay` MUST validate `schema_version`, `workspace_fingerprint`, and `tool_handler_id` against the current
probe before executing, and refuse on mismatch. Given a match, harness decisions are a pure function of the
recorded `raw_response` values plus the pinned workspace and handlers — which is what makes replay deterministic.

### 8.2 Run isolation (lease/state must not leak across runs)

The provenance fields fingerprint the seed files only; they do NOT cover lease/state. `_seed()` overwrites the
workspace each replay but never touches `state_root` (`runs_root/state/patch_leases.json`), so a `runs_root`
reused across runs would inherit stale lease state and corrupt lease-outcome and `deadlock` classification.
Therefore each replay/fixture MUST run in a FRESH, unique `runs_root` (e.g. a per-test `tmp_path`), with both the
workspace re-seeded and `state_root` created empty. No lease or state inheritance across runs. Tests assert a
clean `state_root` at start. (Alternative — clearing `state_root` inside `replay()` — is acceptable only if the
provenance then records and validates the initial state; the fresh-`runs_root` rule is preferred.)

**Replay comparison (timestamps break byte-equality, per I6).** Recorded `lease_before`/`lease_after` snapshots
embed `created_at` and may embed absolute paths, which differ on every fresh run. Replay-comparison tests MUST
therefore assert on the SEMANTIC projection — `owner_id`, `status`, `lease_outcome`, `parse_outcome`,
`replaced`, `done_check`, `termination_reason`, and predicate D — and normalize the run-dependent fields before
comparing: strip `created_at`, and for paths either relativize to the workspace root, replace the `runs_root`
prefix with a stable token, or omit paths entirely (absolutizing does NOT help — a fresh `runs_root` yields
different absolute paths). A raw byte-diff of recorded vs replayed events is NOT a valid equality check.

## 9. Out of scope (recorded, not built)

- Closing ANY surfaced gap, including the §4 orchestration primitives — each becomes its own SPEC-LIVE-NN +
  `ai_tools` ADR after this run ranks them.
- Lease TTL / owner-death reclaim / release-on-failure; worker release actions; cost-cap; typed critic
  contract; model-driven termination; `arguments.tool_name` normalization in `agent_lib` (§3.4).
- Multiple-match routing/scheduling beyond first-match. Any non-local or OS-touching tool.
