# Agent Build Notes — Design Guidance

**Status:** Design guidance (pre-implementation). Not committed decisions except where marked **[boundary decision]**.
**Date:** 2026-05-24
**Source:** Architecture brainstorming session (worker/mentor ASC rebuild, long-horizon autonomy, context management).
**Purpose:** Capture the durable conclusions from that discussion so the next agent-build effort starts from settled reasoning instead of re-deriving it. Read this before expanding `agent_lib` or starting the ASC rebuild.

---

## 0. Governing stance: co-evolution, not speculative maturing

Do not mature `agent_lib` in the abstract ahead of a consuming task, and do not build full apps on a frozen-weak version either. Let the thinnest real task pull the API forward. Each capability is added because a concrete run demonstrably needed it, validated against that run.

**Decision rule:** Build into `agent_lib` when a concrete run fails without it — not when a design conversation suggests it. The brainstorm produces the design; a failed run produces the mandate.

Corollary on what to encode now vs. later:

- **Durable principles** (safe to encode as thin seams): planner/executor separation, gated/escalating oversight, objective verification loops, structured tool/result contracts, patch-over-edit.
- **Volatile mechanisms** (keep swappable, do not bake in): specific multi-agent topologies (swarm/debate), agent-memory architectures, prompting tricks.

## 1. Long-horizon autonomy and roles are one architecture

"Give it a directive and it keeps trying" and "planner/worker/critic roles" are the same loop viewed from two angles. A long loop that survives *is* a set of roles: a planner sets the goal, a worker iterates with tools, a critic checks against objective signals, an escalation role is invoked on stall.

The loop itself (`while not done: act; check`) is trivial and is not where the engineering lives. The real work is four things the loop framing hides:

1. **Failure diagnosis/recovery is capability-bound.** Genuine "try a different way" requires correct failure attribution plus a non-cosmetic alternate hypothesis. Weak/local workers doom-loop here. This is the failure mode, not the edge case.
2. **Context rot.** Long sessions fill with dead ends and error spew; quality degrades without active pruning/summarizing/restarting. See §4–§5.
3. **Stopping is unreliable without ground truth.** Self-assessed "done" stops too early or never. Termination must key off an external verifier (tests, compilation, execution results).
4. **Runaway cost.** Unbounded retrying burns compute. Step caps, cost caps, stall detection are mandatory.

Durable kernel to build (each item a real task will force): a loop with **explicit, swappable termination** (verifier-pass / step-budget / cost-budget / stall-detected); a **progress/stall detector**; **context-management hooks**; a **verifier/critic seam** consuming objective signals; an **escalation seam** gated on verifier-failure-or-stall; **role→engine binding** (already present as `RoleEngineSet`). Do not hardcode a role count, build elaborate topologies, or assume "just keeps going" — termination and escalation are first-class.

## 2. Roles earn their place through asymmetry

More roles is not better; every role boundary is a lossy handoff that adds latency and cost. A role is justified only by **asymmetry** — different capability, context, or authority:

- Planner: broad context + strong reasoning (27B/31B class).
- Worker: focused context + tool access (smaller/faster acceptable).
- Critic: objective signals + judgment (this is the oversight layer).
- Mentor: the escalation role (larger/enterprise model, invoked rarely).

If every role is the same model with the same context, the separation is theater. The asymmetry is what lets expensive capability be spent only where needed.

## 3. Oversight / superego overhead: gate it

Per-step LLM oversight is too expensive for local hardware (roughly doubles inference; on a single 24GB GPU a third co-resident model may not fit, and swapping costs more than the inference). Use **gated/escalating** oversight instead: cheap deterministic checks (policy rules, allow/deny on tool+args) run on every action; the LLM judge fires only when a rule flags ambiguity or a high-risk class.

This mirrors Engram's Reflex→Cognitive split (regex-gated cheap path, escalate to the model only when warranted) — a pattern already proven in this repo. **Reliability tension:** reliable judging wants a large model (per NB02 thresholds), which is exactly the tier you want firing rarely — reinforcing the gating approach.

## 4. Worker/mentor pattern (the ASC rebuild plan)

Planned shape: local **worker** (e.g. Gemma 4 31B at 4-bit, ~18–19GB, fits a 24GB 3090 with modest context headroom) under an enterprise or larger-local **mentor**. This inverts the original ASC (which used Claude Code as the worker); paying the expensive model only for mentorship is the cost win.

Four constraints, all **[boundary decision]** for an ai_tools example:

1. **Mentor is optional and pluggable, never required.** ai_tools is local-first by charter. Worker must run alone (degraded but functional); mentor is an enhancement tier. Demonstrate the *same* abstraction two ways — local-worker/cloud-mentor and local-worker/local-mentor (e.g. 31B mentors an 8B) — so the air-gapped path stays real and the abstraction, not the model, is the lesson.
2. **Escalation gated on objective signals, not worker self-report.** The capability gap is why mentorship helps and why the worker can't be trusted to know it's wrong. Trigger on failed verification (tests/compile/sandbox) or detected stall.
3. **Cost circuit-breaker.** Cap mentor escalations per run. Reuse the shape of `llm_engines` `FailoverPolicy.circuit_breaker_failures`.
4. **Typed worker↔mentor contract.** Mentor returns structured feedback (approve / revise-with-guidance / redirect); worker consumes it deterministically. No free-text re-parsing.

**Sequencing caveat:** `agent_lib` is experimental and MEMBERSHIP gates ASC on it reaching beta. Treat the first ASC pass as a *probe into the API* — the example drives the contract — not a finished example.

## 5. Context management is the long-session problem (not capacity)

Two distinct "context size" problems; do not conflate them:

- **Memory cost of context** (VRAM per token of KV cache). Addressed by KV-cache quantization.
- **Context rot** (window fills with stale state, failed attempts, redundant output; quality degrades). This is the agent enemy.

**TurboQuant** (Google Research, 2026; ~3-bit KV-cache vector quantization, no retraining) solves only the *memory cost*. It does nothing for rot, and by enlarging the window it can *encourage* hoarding of junk. Community implementations are vLLM-only (off the Ollama default path), research-grade, with measured benefit (~2x on dense models) below the ~5x headline. **[boundary decision]** If used at all, it is an inference-layer optimization for `llm_engines`/vLLM backend config — **not** `agent_lib`, and not the answer to long-session reliability. The cheaper available lever for raw capacity on the 3090 is llama.cpp KV-cache quantization plus context pruning.

## 6. Context-rot reduction reuses Engram primitives

The context-management seam is largely composition, not new machinery.

**Reusable primitives (live in `engram`):** near-duplicate blocking, retrieval-time diversity filtering, canonical correction / tombstoning (cosine ~0.92), `detect_contradiction`, two-scale recency normalization. Mapping:

- redundant retries / repeated tool output → dedup + diversity filter
- stale superseded state (file edited twice, etc.) → canonical correction / tombstoning
- contradictory entries → contradiction detection, drop the superseded side

**Agent-specific policy (lives in `agent_lib`):** **[boundary decision]** the primitives stay in `engram`; the policy stays in `agent_lib` — pushing agent policy into `engram` violates the package boundary (memory ≠ orchestration). `agent_lib` already has `EngramMemoryAdapter`, so the wiring exists. The policy must handle four things the memory case does not:

1. **A failed attempt is not noise** — compress it *to its lesson*, do not delete it, or the agent re-tries it (doom loop). Dedup decides redundancy; an agent-side reducer decides drop-transcript-keep-outcome.
2. **Threshold retuning** — 0.92 is tuned for episodic memory; tool outputs/traces differ (two stack traces can be 0.95 similar but a differing line number is load-bearing).
3. **Preserve causal sequence** — agent context has a causal narrative; dedup must not reorder or remove load-bearing middle steps.
4. **Recency weighting matters more** — current state outweighs early exploration.

## 7. What to do first

Everything above converges on one cheap first move:

1. Hand-build **one** `language_tutor` capability against the refreshed public API (also the API acceptance test for the stable packages — see MEMBERSHIP step 4).
2. Stand up a minimal worker/mentor loop against that slice as a **fixed target with known-correct output**. An orchestrator is far easier to develop and verify when the task has a ground-truth answer, and it gives the loop the objective escalation signal §4 requires.
3. Let it run long enough to rot, and **capture the transcript**. That transcript is the evidence that pulls in the §6 reducer and the §1 kernel — co-evolution, per §0.

Do not build the §6 reducer or the §1 kernel before step 3 produces a real transcript. The brainstorm tells you *how* you would build them; a failed/rotted run tells you *that* you must, and with what policy.

## 8. Future: dedicated agent orchestration repo

The `examples/agent_coordination_teaching` example is correctly scoped as a
teaching artifact — it demonstrates `agent_lib` coordination primitives and is
intentionally narrow. A more extensive capability, implementing the worker/mentor
pattern in §4 as a real orchestrator, belongs in its own repository as a peer
to `ai_tools`, not inside it.

**Shape:** a standalone repo that consumes `ai_tools` packages as library
dependencies (same pattern as the planned course split). Its design brief is
already written — §§1–6 above plus ADR-011.

**Trigger:** start the repo when a concrete task makes `agent_coordination_teaching`
demonstrably insufficient. A natural candidate: point the coordination example
at the `language_tutor` rebuild and note where the single-pass dispatch breaks
down. That failure is the evidence base for the first commits.

**Non-negotiables from day one** (do not retrofit):

- Isolation per ADR-011's recommended baseline: rootless container, workspace
  bind-mounted read/write, `--network none` by default. The lesson from
  `agent_coordination_teaching` is that sandboxing added late is sandboxing
  applied inconsistently.
- Worker/mentor wiring with an optional, pluggable mentor (§4 boundary
  decisions). The cloud mentor must never be required — the local-only path
  must degrade gracefully, not fail.
- Objective escalation triggers only (§4) — no self-reported "I am stuck."
- Cost circuit-breaker on mentor calls from the first session that uses a
  cloud mentor.

**What `examples/agent_coordination_teaching` provides to bootstrap it:**
the coordination primitive patterns (mailbox, ExternalSessionCoordinator,
exchange log, monitor), planner/worker wiring, and the isolation gap inventory
documented in that example's API_CHANGES.md and README.

**Inference-optimization findings that apply directly** (see
`docs/design/INFERENCE_OPTIMIZATION.md` §3a and §6): `session_id` is necessary
but not sufficient for shared-prefix workers (a layered prefix key is the
eventual need); KV-cache contention is a hard concurrency limit on a single
local GPU, mitigated by RAM/NVMe tier offload; aggregated `CacheStats` becomes
the fleet-level scheduling and debugging signal; the cost circuit-breaker
should be expressed in dollars (from cache hit ratios), not call count; and the
shared-vs-per-agent Engram memory choice now carries a cost axis as well as a
correctness one. Instrument cache telemetry from the first session that runs
real concurrent workers.

---

## Reference

This document distills a design discussion held 2026-05-24, with §8 added
2026-05-27 after `examples/agent_coordination_teaching` was completed. It is
guidance for a future build, not a record of work performed. When the dedicated
agent orchestration repo is started, begin with §§1–6 and ADR-011, then update
or supersede sections as real runs provide evidence. Related:
`docs/design/VISION.md` (harness principles), `docs/internal/MEMBERSHIP.md`
(execution sequence), `adr/ADR-011-agent-execution-isolation.md`.
