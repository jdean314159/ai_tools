# SPEC-ASC-00 — ASC Phase 0: Verify-Then-Probe the Worker/Mentor Loop

**Status:** Draft for Codex.
**Depends on:** `docs/design/AGENT_BUILD_NOTES.md` §4 (worker/mentor plan), ADR-011
(agent-execution-isolation, with "open questions deferred to first ASC run"),
`docs/internal/MEMBERSHIP.md` (ASC is an example built with `agent_lib`; gated on
`agent_lib` reaching beta — and the first pass is the probe that drives it there).
**Discipline:** `docs/internal/REPO_STATE_VERIFICATION.md` — a filename/class name is a lead, not a fact.
Resolve every "exists/absent" claim by READ + TEST, never by name-grep.

---

## 0. Why this is verify-then-probe, not build

A surface scan shows the worker/mentor loop is **substantially already present** in
`agent_lib`, under planner/executor/**critic** naming — not absent:

- `runtime.py`: `AgentRuntime(planner, critic=...)`; `_should_escalate(run)` flips
  `active_controller` to `"critic"` on an objective `needs_critic` signal and swaps
  `active_planner = self.critic` (the critic engine is actually invoked, not just flagged);
  `run.escalations` counted; `StopReason` includes `critic_completed`.
- `llm_engines_adapter.py`: `RoleEngineSet(planner, executor, critic)` with critic→planner
  fallback (mentor optional).
- `programming.py`: `ProgrammingFailureController` sets `needs_critic` on failed
  `run_check`/`run_command` (objective verification failure, not worker self-report);
  `WorkspaceIsolationManager` provides git-worktree / copy / container isolation;
  `FailurePolicy` with retry/escalate/stop; CLI `--mentor`/`--worker`/`--critic` bindings.

So building a parallel worker/mentor system would duplicate existing code — the exact
false-absent error REPO_STATE_VERIFICATION guards against. Phase 0's job is to (A) confirm
what the existing loop does against the §4 constraints and ADR-011's deferred questions by
reading and testing it, and (B) run it on a low-stakes refactoring fixture to surface which
boundaries actually bite. Only gaps the probe forces become a build list.

---

## Part A — Verify the existing loop against the §4 constraints (READ + TEST)

For each, state: **met | partial | gap**, with the file/function read and the test run as
evidence. Name-grep alone resolves nothing.

| # | §4 constraint | Where to look | Confirm |
|---|---|---|---|
| 1 | Mentor optional/pluggable; worker runs alone (degraded but functional) | `RoleEngineSet` critic→planner fallback; `AgentRuntime` with `critic=None` | Run a task with `critic=None`: completes (no escalation path crashes). Run with a distinct critic engine: escalation invokes it. Both the local-worker/cloud-mentor AND local-worker/local-mentor wirings are expressible (31B mentors 8B) — confirm the abstraction is model-agnostic, not just one config. |
| 2 | Escalation gated on objective signals, not worker self-report | `runtime._should_escalate`; `programming.ProgrammingFailureController` setting `needs_critic` | Confirm `needs_critic` is set by failed `run_check`/`run_command` verification, NOT by the worker declaring itself stuck. Test: a worker action that fails verification escalates; a worker that merely *says* "I need help" without a verification failure does NOT. |
| 3 | Cost circuit-breaker (cap mentor escalations per run) | `run.escalations` counter; `programming.FailurePolicy`; compare to `llm_engines` `FailoverPolicy.circuit_breaker_failures` | **Confirm whether a cap exists that STOPS the run.** Escalations are counted — is there a ceiling that halts (not just counts)? If counted-but-uncapped → **gap** (likely build item). |
| 4 | Typed worker↔mentor contract (approve / revise-with-guidance / redirect), consumed deterministically | `runtime.py` critic path; `contracts.py` | **Confirm the shape of critic feedback.** Currently the critic appears to take over as planner (implicit "redirect"). Is there a typed three-way result (approve / revise-with-guidance / redirect) the worker consumes deterministically, or is it free-text-as-next-plan? If the former is absent → **gap** (likely build item). |

ADR-011 deferred isolation questions (resolve against `WorkspaceIsolationManager` +
`execute_workspace_command` + `_build_container_command`):

- Which isolation mode is the default, and is sandbox *fallback* reported as **degraded
  execution, not clean success** (AGENT.md safety invariant)? Test it.
- Is path resolution confined to the workspace root (invariant)? Test a `../` escape attempt.
- Empty `WorkspacePolicy.writable_paths` ⇒ no write permission (invariant)? Test it.
- `runnable_commands` exact allowlist enforced? Test a non-allowlisted command is denied.

Part A output: a filled table (met/partial/gap + evidence) and the ADR-011 question answers.
This alone is valuable and is the REPO_STATE_VERIFICATION pass for the agent layer.

---

## Part B — The refactoring-fixture probe (low-stakes, observable)

Do NOT target the example projects (diagnostics_agent is gated; netflow is correctness-
critical; language_tutor is mid-rebuild; agent_coordination_teaching is the ASC draft
itself). Build a **purpose-made, disposable fixture** so wrong output is free.

### B1. Fixture module + characterization tests (tests FIRST)

Under `examples/asc_probe/fixture/` (gitignored working area for ASC runs, like netflow
`data/`): a small Python module with deliberate, verifiable refactoring opportunities, and a
**characterization test suite written first** that pins current behavior. The refactor is
"safe" only against this suite; behavior must be identical after each task.

### B2. Difficulty ladder (so the escalation gate produces signal)

Grade tasks so you can read constraint #1/#2 — if every task escalates you can't tell "gate
works" from "worker hopeless"; if none does, the mentor path is untested:

- **Solo-tier** (local worker should complete alone): rename a symbol; extract a constant;
  add type annotations; collapse an obviously duplicated branch.
- **Escalation-tier** (should trip objective verification → critic): a refactor that breaks a
  characterization test unless a cross-module invariant the worker can't see is preserved
  (e.g. a change that passes locally but violates a contract the test enforces).

Record per task: completed solo / escalated-and-recovered / escalated-and-failed / wrong-
but-tests-green (the dangerous case — a refactor that passes tests but is non-idiomatic or
semantically worse; flag for human judgment, since tests are necessary-not-sufficient here).

### B3. Harness

A minimal `examples/asc_probe/run_probe.py` that stands up the EXISTING
`AgentRuntime`/`RoleEngineSet`/programming runtime with a worker engine and an optional
critic engine, points it at the fixture + ladder, runs under the configured isolation mode,
and emits a per-task record. Reuse `programming.build_programming_task` and the existing
verification-command mechanism; do not reimplement the loop. Worker model per AGENT_BUILD_NOTES
§4 (e.g. a 4-bit ~31B that fits the 3090); critic optional (run once worker-only, once with a
larger mentor) to exercise constraint #1 both ways.

---

## 1. Hard stops / boundaries

- This is a **probe into the existing API**, not a finished ASC example (AGENT_BUILD_NOTES
  §62). The deliverable is "what bit," not a coding assistant.
- `agent_lib` stays experimental; do not promote it or add public API surface in this pass.
  Gaps are recorded, then built only if Part B forces them (build-when-forced).
- Fixture + run artifacts live in a gitignored working area; nothing ASC-generated is
  committed without human review. The example projects are not touched.
- No new parallel worker/mentor system — extend/drive the existing programming runtime.

---

## 2. Done criteria

- [ ] Part A table filled: each §4 constraint met/partial/gap with file read + test run as
      evidence (not name-grep). ADR-011 isolation questions answered with tests for each
      AGENT.md safety invariant (writable_paths, runnable_commands, path confinement, sandbox
      fallback reported as degraded).
- [ ] Fixture module + characterization tests (tests written first) under gitignored area.
- [ ] Difficulty ladder implemented (solo-tier + escalation-tier tasks).
- [ ] `run_probe.py` drives the EXISTING runtime (worker-only and worker+mentor); no
      reimplemented loop; runs under the configured isolation mode.
- [ ] Per-task records: completed-solo / escalated-recovered / escalated-failed /
      wrong-but-tests-green. The last category explicitly surfaced for human review.
- [ ] **Gap list**: only the §4 constraints Part A found partial/gap AND Part B exercised —
      each with the concrete run that failed without it. Cost-cap (#3) and typed
      approve/revise/redirect contract (#4) confirmed present or recorded as forced gaps.
- [ ] Tests pass; `python -m compileall -q agent_lib`; `git diff --check` clean.

---

## 3. Report-back

Part A verdict table + ADR-011 answers. Part B ladder outcomes: how many solo-tier completed
alone (constraint #1 holds), whether escalation-tier tripped the critic on objective signals
(constraint #2 holds), any wrong-but-tests-green cases (the oracle-weakness finding). Then the
forced-gap list with the failing run for each — that list, not this spec, decides what gets
built next.
