# ai_tools — Session Handoff (for new thread / Codex)

**Date:** 2026-06-15
**Read order for a new thread:** this file → `docs/internal/STATUS.md` → `adr/ADR-016` → `docs/design/DECISION_HISTORY_SCHEMA.md`.
STATUS.md is the standing state; this file is "what just happened and the next action."

---

## TL;DR

## Update — 2026-06-21 (COORD campaign closed; checkout workflow)

**Repository state at handoff:** `ai_tools` is clean on `codex-cleanup-pass` at
`3dceb3e` (`WIP: accumulated multi-thread work pre-curation`), following:

- `ed73f04` — coordination control plane;
- `a057e76` — unified atomic path ownership; and
- `3dceb3e` — deliberate multi-thread WIP consolidation.

`backup/pre-curation-20260621` anchors `a057e76`. Nothing in this campaign has
been pushed. `computer_helper` contains the matching probe commits, including
`c0a416e` (`test(probe): verify unified path ownership`), but its worktree still
has pre-existing staged/untracked probe-state changes; inspect it before making
any unrelated commit there.

**COORD campaign: CLOSED.** All four ledger gaps are closed. ADR-017 established
capability routing, per-session tool grants, and the coordinator deny-all guard.
ADR-018 then unified path ownership: manager-backed coordination uses one
cross-process-locked lease authority for both reservations and write enforcement;
the no-manager mailbox remains explicitly advisory-only for compatibility. The
library and probe commits are separate. Targeted `agent_lib` tests (73) and
`computer_helper` tests (6) passed, as did compile and diff checks.

**Open threads (none urgent):**

- Write a tracked digest for the neural-eval results if neural work resumes;
  the `affinity_weight=2.1` recall-collapse evidence currently exists only in
  the untracked `runs/` tree.
- The thematic curation of `3dceb3e` is intentionally deferred unless a future
  bisect or revert needs it.
- A deterministic control plane and unified ownership now make a live
  multi-agent run the natural next campaign. It remains out of scope until a
  new mandate.

**Workflow rule:** do not run multiple work streams in one checkout. Create a
branch (and, when concurrent, a separate worktree) per stream; it prevents
staged/index overlap and preserves independently reviewable commits.

**Specification process fix:** apply the `AGENTS.md` spec-and-planning policy
(lines 22–28) before review: cite every reuse claim from its actual call path,
separate unverified assumptions from confirmed facts, and name machinery that
must be built because it does not exist. This turned LIVE-00 from repeated
design corrections into clean review passes; carry it into every future spec.

Two threads closed this session, both landing on "don't build the big thing."

1. **Neural memory campaign is COMPLETE and the layer is PARKED.** The
   RTRL/TITANS layer (NEURAL-01 -> 06) was fully implemented, evaluated, and
   parked default-off as a research artifact. It did not earn core-feature
   status: re-ranking was rejected on catastrophic recall loss, and the
   TITANS-style prompt synthesis returned a clean null in generation-mode eval.
   ADR-016 is the decision record.
2. **Knowledge-curation MVP resolved AGAINST a wiki/adjudicator subsystem.** A
   three-phase probe showed an LLM adjudicator is untrustworthy and the value
   lives entirely in structured metadata. The shipped capability is a small
   deterministic decision-history schema + validator, NOT a memory subsystem.

Nothing is mid-flight in code. Remaining items are backlog.

## Update — 2026-06-15 (latest session)

No repo code changed this session. Two things happened:

1. **The two open verification items (see Next action) were checked — both
   pass.** The CI decision gate skips (not fails) ADRs without a
   decision-history block (`validate_decision_history.py`: `if payload is None:
   continue`), and `DECISION_HISTORY_SCHEMA.md` states the opt-in adoption rule
   explicitly. Both prior "Next action" items are now closed.
2. **Netflow campaign extracted:** `netflow_behavior_lab` now lives in the
   sibling repo `../netflow_behavior_lab`; it is no longer an `ai_tools`
   example. Deterministic flow-metadata
   host-behavior pipeline, local LLM as grounded interpreter only (never the
   trust surface). Dataset sequence **CTU-13 -> NF-UNSW-NB15 -> NPS** (two
   public benchmarks first for direct comparison with other researchers; NPS
   local-only, for the OS/behavioral claims its labels uniquely support).
   Not a novel-algorithm project; paper, if any, via survey / education /
   constraint-driven systems framing. Full detail:
   `../netflow_behavior_lab/notes/PLAN_netflow_behavior_lab.md` +
   `../netflow_behavior_lab/notes/HANDOFF_netflow_behavior_lab.md`.

## Thread 1 — Neural memory: landed, then parked

All specs implemented by Codex and validated green. Final disposition in
ADR-016. The arc:

- **NEURAL-01** — additive `MemoryLayer` protocol + 4 seams in `ProjectMemory`
  (observe / contribute_to_recall / contribute_to_prompt / persist+close),
  advisory-only, default-empty registry. Four existing layers untouched.
- **NEURAL-02a/02b** — vendored RTRL/TITANS core into `engram/neural/`; numpy
  default, torch optional via `[neural-accel]`. `NeuralMemoryLayer` as first
  MemoryLayer; `enable_neural=False` default.
- **NEURAL-04** — affinity made scale-invariant (spread-relative); affinity
  weight moved to config (0.15 default).
- **NEURAL-05** — **re-ranking disabled** after two clean runs showed
  catastrophic direct-recall loss at every weight. Surprise repurposed to
  write-side episode-importance (bounded, advisory, never suppresses).
- **NEURAL-06** — TITANS-style prompt-hint synthesis: value-projector
  pseudoinverse -> episode alignment -> template `[Neural context]` hint.
  `value_dim` 16->64 attempted but **reverted to 32 on RTRL overflow**
  (600-step stability test); `hidden_dim` stays 32 (P-matrix overflow).
  Config versioned (now v3); non-finite neural state fails closed (halts
  reads/writes/hints).

**NEURAL-06 generation-mode eval (2026-06-11): clean null.** qwen3:8b
generator, qwen3.6:27b judge, 60-fact corpus, 6 trials, 1 warmup replay,
baseline vs neural_on. Hints emitted 180/180 per trial, warmup at 120 steps —
**mechanism confirmed working end-to-end** — but every metric delta within 1-2
judgments of baseline (recall_direct 0.878->0.872, paraphrase 0.861->0.858,
decoy 0.250->0.239, bleed unchanged). Decoy is structurally uninformative in
generation mode (unconstrained generator answers from parametric memory
regardless of hints).

**Decision: layer PARKED** (ADR-016 final section). Default-off behind the
NEURAL-01 seam, not actively developed. A reframe was identified but NOT
pursued: the layer's distinctive output is its label-free surprise signal,
which suits novelty/anomaly use (agent-loop derailment, memory-poisoning
detection, surprise-based segmentation) rather than retrieval. **Reactivation
requires a concrete safety/observability need plus a predeclared falsifiable
gate. Do not re-run retrieval evals without a new mandate.**

## Thread 2 — Knowledge-curation MVP: resolved against a subsystem

Question explored: could conversation history (conversations.json, ~10.7k
messages) be curated into an evidence-linked memory that preserves *how
conclusions changed*? Three probes settled it empirically:

- **First extraction** (323 candidate claims): mechanically fine (parsing,
  provenance to message UUIDs) but a competent index, not a memory — uniformly
  agreeable claims, no contradiction detection, `source_material` label
  masquerading as an authority signal.
- **Phase 5B** (adjudication probe, pre-declared gate): LLM adjudicator FAILED
  — collapsed nuance toward single labels, both over-killing live claims
  (`historical`) and over-crediting unsupported ones (`qualified`).
- **Phase 5C** (strategy comparison): zero-shot 6 errors, few-shot 4 errors
  (but MORE unsupported links), few-shot+policy 0 errors / 6 unsupported links,
  **deterministic-only 0 errors / 0 unsupported links**. The deterministic path
  dominated on every axis.

**Decision: no LLM adjudicator.** Value lives in structured metadata, not
interpretation. Shipped capability:

- `docs/design/DECISION_HISTORY_SCHEMA.md` — YAML front-matter schema for ADRs.
- `scripts/validate_decision_history.py` — strict validator.
- ADR-016 carries the proof case: four scoped `(id, application_scope)` records.
- `make check-decisions` + CI doc gate. Knowledge-MVP suite: 43 passed.

**Schema invariants (do not relax):** closed enums + paths drive logic; free
text (`basis`, `current_guidance`) is display-only; keys are
`(hypothesis, application_scope)` not bare hypotheses; `mechanism_status`
(operational/not_demonstrated/not_applicable) records *did it function*,
orthogonal to `resolution_status` (*did it help*); `mechanism_evidence`
required iff `operational`; heading fragments must resolve to exact
GitHub-style slugs; contradiction detection is exact-key collision only;
validator confirms references resolve, NOT that claims are true.

**Adoption is incremental and opt-in:** a decision-history block is added when
an ADR records a superseded hypothesis or split-application resolution — NOT
required on every ADR. The CI gate must skip ADRs without the block, not fail
them. (VERIFY this is how the gate is scoped.)

## Decisions closed (do NOT re-litigate)

- **Neural re-ranking: rejected** (catastrophic recall loss, two clean 27b
  runs). `contribute_to_recall` returns None.
- **Neural layer: parked, default-off.** Not core. Reactivation needs a new
  concrete need + predeclared gate. The promising-looking reframe
  (novelty/anomaly via surprise signal) is untested and explicitly NOT a
  mandate to build.
- **value_dim stays 32, hidden_dim stays 32.** 64 caused RTRL/P-matrix
  overflow; reverted. Documented in ADR-016 as a superseded parameter change.
- **No LLM knowledge adjudicator.** Phase 5C proved deterministic metadata
  strictly dominates. LLM may assist *ingestion* but its evidence links are
  untrusted candidates only.
- **The decision-history schema is the knowledge capability** — a metadata
  convention with no trust surface, not a subsystem. The arc-preservation value
  (why a hypothesis was tried + how it resolved) is captured at decision time,
  deterministically.

## NetFlow campaign — done and recorded:

Phases 0–5 complete. Mechanism: rare external-destination breadth of malicious activity drives the rank — not C2 concentration (rejected via cc_only, 7 scenarios), not a same-host artifact (refuted by subtractive collapse + three independent hosts co-ranking in Sc.12). Validated across Neris/Rbot/Virut/DonBot + NSIS.ay (P2P). Blind spot characterized empirically: narrow-fan-out C2 (the cc_only profile, ranks 60–349).
SPEC-NETFLOW-00 through 05 now live in `../netflow_behavior_lab/specs/`, results recorded in each.

## Open / queued:

SPEC-NETFLOW-06 (NPS real-network) — extracted to `../netflow_behavior_lab/specs/`; operating under the §2a conservative fallback (NPS internal ranges + VPN-partner subnets not authoritatively known). Hard gates before ranking: internal-range list, adjudication authorization, NAT confirmation. Outside-firewall capture identified NPS public space (205.155.65.x, 204.102.229.x); blocked_fraction from the firewall-policy dataset folded in as an adjudication evidence line, not a ranking input.
REPO_STATE_VERIFICATION.md — checklist queued, not executed. First task flagged: the turboquant.py path discrepancy (asserted built, failed ls in the snapshot — resolve real-absence vs stale-copy first).

Two unverified facts the next thread must not inherit as settled:

The repo snapshot I was reading may lag your working tree — the turboquant discrepancy could be that.
Everything in the repo-state assessment is lead-not-fact until the verification checklist runs.

## Deferred backlog (none blocking)

- **Course-repo extraction** — teaching material (course/, docs/learning/)
  moves to a separate repo; severs library<->course cross-references. Library
  READMEs must never link to course material (dependency direction is
  course->library). Gated behind public-API stability.
- **TOPOLOGY-01 conversion** — single-distribution decision (Option A) made;
  ADR-015 + conversion deferred until after course-repo extraction.
- **Neural backlog (only if reactivated under a new mandate):** torch-accel
  parity test; SurpriseFilter (needs logprob engine); novelty/anomaly reframe
  probe; corpus expansion (`fact_generator.py` is a stub) if a future retrieval
  mandate appears.
- **SPEC-CLASSIFY-01/02** — engram conftest import trap; diagnostics test
  isolation. Parked.

## Standing context

- Workflow: Claude writes specs/reviews; Codex implements + runs evals on the
  RTX 3090 workstation. ADRs + this handoff are the cross-thread memory.
- ADR-016 is the neural layer's decision record AND the decision-history schema
  proof case. Both threads converge there.
- Recovery bundles (if needed): neural subsystem + eval harness were recovered
  from git history at `84f4f86~1`. Live repo contains the adapted versions.
