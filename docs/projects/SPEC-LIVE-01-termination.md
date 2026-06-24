# SPEC-LIVE-01 — Predicate-Driven Termination (probe-side fix)

**Status:** Ready to implement. Option 1 ratified (probe-side fix; `agent_lib` untouched).
**Covers:** Closing Finding 1 from SPEC-LIVE-00 — the run overran to `step_cap` after the
authoritative done-check was already satisfied, because termination depended on the model
volunteering `{"done": true}` rather than on the predicate.
**Depends on:** SPEC-LIVE-00 (v8, `74bf4bc`); Finding 1 confirmed in-tree on the v8 harness
(`computer_helper` `7e40b36`, run `runs/live_00_v8_20260624/`).
**Mode:** LIVE with deterministic REPLAY, same as LIVE-00. The fix is verified by deterministic
fixtures; a live re-run confirms the model path still reaches done and now terminates on it.
**Discipline:** Probe lands in `~/repos/computer_helper` ONLY. This change adds NOTHING to
`agent_lib`. The library's lack of an execution loop / termination contract is recorded as a
standing gap, not closed here (see "Why probe-side").
**Governing rule:** Gate on the orchestrator's RESPONSE to a satisfied predicate, never on the
model's correctness. The model emitting or omitting `{"done": true}` must not change the stop.

---

## 1. Finding 1, restated (single source)

Confirmed under the v8 harness: at step 2 the worker retrieved the canonical value; at step 4 it
wrote `config.toml` to `1.2.0` and the authoritative done-check became satisfied; the coordinator
then issued four more `replace_text` routes (steps 5–12) and the run terminated at `step_cap`, not
`done`. Code cause: `termination="done"` is set only when the coordinator volunteers `{"done":
true}` and `_done()` validates it (`live_probe_00.py:257–262` on the v8 branch); a satisfied
predicate alone never
terminates the loop.

## 2. Decision — Option 1 (ratified)

Fix termination **in the probe orchestrator**. The probe loop consults the authoritative `_done()`
predicate each step and terminates the run the moment it is satisfied. The model's `{"done": true}`
is demoted from any termination role to **purely informational**: it may be recorded when seen (for
transcript/observability), but it never controls termination — it can neither stop a run whose
predicate is unsatisfied nor hasten one whose predicate is satisfied (the predicate already stops
that run on its own). The model signal and the stop decision are fully decoupled.

This makes the termination contract explicit and probe-owned: **the authoritative predicate is the
sole driver of the stop; the model signal is advisory and inert.** That is the contract that
generalizes; the loop that hosts it does not (see §5).

## 3. Why probe-side, not in `agent_lib` (grounded)

`agent_lib/src/agent_lib/coordination.py` has **no execution loop**: no `run`/`step`/`terminate`/
`done`. `ManagedCoordination` (line 287) is a three-field dataclass (`coordinator`,
`isolation_manager`, `worker_runtimes`). The probe builds the entire loop and owns the termination
decision. "Predicate-driven termination as an `agent_lib` change" would therefore be a
**consumerless primitive** — there is no in-library caller to terminate — which is the
anti-probe-first pattern. So termination is fixed where the loop actually lives: the probe.

The library gap ("no execution loop / no termination contract") is recorded as a **standing gap**,
not closed. It is NOT promoted to an `agent_lib` change by this spec.

**Watch-flag for a future reversal:** Option 1 holds *because `computer_helper` is currently a
probe* — a gap-surfacing harness, not a durable consumer, so its loop is throwaway and belongs in
the probe. If `computer_helper` graduates into the actual product (a real, maintained consumer
rather than an experiment), its loop stops being throwaway and the calculus for moving orchestration
into `agent_lib` changes. Re-open the Option 1 vs Option 2 question if that graduation happens; do
not treat this spec as having settled it for that future.

## 4. The provisional second-consumer rule (do not pre-commit an API)

A shared termination primitive is extracted into `agent_lib` only when a second consumer shares a
contract shape that is painful to keep in sync — and even then, the API shape is decided at that
point, not now. This remains a provisional design rule, not a commitment. The arrival of a second
consumer is a **prompt to re-evaluate**, not an automatic mandate to extract; two consumers that
keep their contracts cheaply in sync need no shared primitive.

Rationale, held as a HYPOTHESIS not a finding: the planned consumers (a novel-tool agent, the
language tutor, `computer_helper`) may each need *a* loop but not the *same* loop — topologies could
differ (capability-routed alternation vs critique pipeline vs plan-then-execute). What is more
confidently expected to generalize is the termination *contract* (predicate authoritative, model
signal advisory); the loop may or may not. Caveat: many agent loops collapse to the same skeleton
(dispatch → observe → check predicate → stop-or-continue) with the variation living in routing
policy, which is already separable — so the loop may generalize more than assumed. Do not act on the
"loops differ" claim as settled; the second consumer will reveal it for free. Extracting on the
first consumer would freeze an API shape against a single topology, which is the concrete reason to
wait, independent of how the hypothesis resolves.

## 5. Invariants

- **T1 (predicate authority):** the loop terminates with `termination="done"` on the first step at
  which `_done()` is satisfied, regardless of any model signal that step or prior.
- **T2 (signal is inert):** a model `{"done": true}` never terminates the loop and never extends it.
  It may be recorded as an observed signal, but the stop decision is made solely by `_done()`. There
  is no case in which the model signal changes when the loop ends.
- **T3 (no regression of LIVE-00 gates):** predicate D and FX-CONTENTION behavior are unchanged —
  those runs never satisfy `_done()` (no canonical write), so T1 cannot short-circuit them, and they
  must still classify as deadlock at `step_cap`.
- **T4 (step_cap remains a backstop):** `step_cap` still terminates runs where `_done()` is never
  satisfied; this spec changes only the satisfied-predicate path.

## 6. Test gate (deterministic)

- **FX-DONE-IMMEDIATE:** seed a run where the predicate is satisfied at the step the canonical write
  lands; assert termination is `done` at that step, not `step_cap`, and that no further routes are
  issued. This fixture failing on the current code (it overruns to `step_cap`) is the gate — it is
  the actual proof of the contract (predicate drives the stop).
- **FX-DONE-PREMATURE-SIGNAL:** model emits `{"done": true}` on a step where `_done()` does NOT hold
  → signal does not terminate; loop continues and is recorded as an observed-but-inert signal (T2).
  This is the only signal-specific fixture needed: it proves the model cannot stop a run the
  predicate has not stopped. There is deliberately no "signal-when-already-done terminates" fixture —
  under T1 the predicate has already stopped that run, so such a fixture would test nothing
  independent.
- **Regression:** the existing FX-CONTENTION and predicate-D replay fixtures must remain green
  unchanged (T3).

## 7. Live confirmation

Re-run the v8 harness live against the local qwen3:8b: the success path must now terminate `done` at
the step the canonical write satisfies the predicate (the four trailing `replace_text` routes from
the Finding 1 transcript must not occur). Record the new transcript/ledger as the in-tree
confirmation that the fix closes Finding 1 on the model path.

## 8. Cross-repo delivery

Probe + this spec land as coordinated commits in their respective repositories, each
cross-referencing the other commit (the LIVE-00 reciprocal-reference rule). The standing
library-gap note ("no execution loop / no termination contract; provisional second-consumer
extraction rule") is recorded in the handoff, not as an `agent_lib` change.
