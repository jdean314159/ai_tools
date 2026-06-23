# Self-Improvement in ai_tools — Design Note and Readiness Finding

**Status:** Design note, NOT a spec. Scopes what self-improvement could be, what it must not repeat, how it
would be tested, and — grounded in the current repo — why it is not yet buildable. No implementation is
authorized by this note.

**Framing:** Self-improvement is the most seductive candidate for the failure mode this project has twice
avoided (neural retrieval, the LLM knowledge-adjudicator): it sounds valuable, is hard to falsify, and has no
natural failure surface. A system that does not self-improve produces no failing run, so the usual probe-first
trigger ("build when a concrete run fails without it") does not apply. The discipline therefore inverts: the
falsification condition must be *manufactured and predeclared* before anything is built, the way ADR-016
required a predeclared gate for neural reactivation. This note's primary job is to install that gate.

## Readiness finding (grounded, 2026-06-22)

A self-improvement loop promotes *recurring* patterns into authoritative rules/skills. Recurrence is the
load-bearing signal. The current repo has none to test against:

- 17 ADRs; exactly **one** (ADR-016) carries a decision-history block.
- That block holds **four records, all the same hypothesis** (the neural memory layer) split across four
  `application_scope` values (retrieval-re-ranking, write-side-episode-importance, prompt-side-context,
  novelty-anomaly-detection). One decision, finely decomposed — the split-resolution case the schema was built
  for, NOT a pattern recurring across independent decisions.
- There is no cross-decision recurrence in the corpus, and no operating-session learnings store at all.

Root cause (as the maintainer put it): the work has been **building `ai_tools`, not using it.** The
decision-history schema records build-time decisions, applied opt-in, once so far. A self-improvement loop feeds
on *usage* — accumulated patterns from operating the system across many sessions — and that substrate does not
exist. (The `diagnostics_agent` "grow libraries through use" campaign is eval-driven, not accumulation of
promotable cross-session patterns.)

**Conclusion: the retrospective probe (below) cannot be run now.** Not because it is small — because recurrence
is structurally absent. This is a legitimate not-yet, not a build-on-faith.

## What self-improvement could be (target architecture, deferred)

The trustworthy design is already half-shipped and half-borrowed:

- **Your half (the gate):** the decision-history schema + `validate_decision_history.py` + CI gate is a
  deterministic, validated record of how conclusions changed. This is the corpus a loop would read — already
  validator-gated, unlike a free-form learnings log.
- **The borrowed half (the loop):** the sibling system's log → read → promote → extract pipeline
  (`docs/internal/LESSONS_FROM_OPCOM.md`, Lessons 1/6 context). `ai_tools` has no such loop.
- **Synthesis:** the sibling's pipeline + your deterministic validator. Promotion is gated by *mechanically
  verifiable recurrence against the corpus*, never by model judgment that a pattern is "proven."

Gate boundary (from the trust discussion): loose everywhere upstream — agents reasoning, drafting, proposing,
critiquing run free; one hard deterministic check at the single promotion door (does this pattern's recurrence
actually verify against the record). One gate, not a hundred. Looseness is cheap and visible upstream; a bad
promotion is durable and silent, so only that boundary is gated.

## What it must NOT be (settled, do not relitigate)

- **No LLM adjudicator deciding what is "proven."** Phase 5C found LLM adjudication untrustworthy and
  deterministic metadata strictly dominant; this holds regardless of model strength — a stronger model lowers
  the error rate, not the failure mode, and the promotion-on-recurrence sub-task is counting-over-records, the
  thing models are least reliable at. An LLM may *surface candidates*; its judgments are untrusted.
- **No neural / surprise-based "learning" reactivation** here; that is parked and needs its own mandate (ADR-016).
- **No promotion that is not mechanically verifiable** against the decision-history corpus.

## How it would be tested (nested gates, when ready)

1. **Retrospective evaluator (the minimal, cheap probe).** A deterministic script reads the existing
   decision-history corpus, finds patterns meeting a recurrence threshold, and *proposes* promotions. No model
   in it. Score against a human-labeled held-out set: did deterministic promotion surface rules a reviewer
   endorses that were not already rules? This tests the only part that carries trust (the gate), with no live
   loop and no accumulation wait. Cost is real and human: the maintainer (not a model — that would reintroduce
   the surface under test) must label the ground-truth set.
2. **Predeclared bar.** The loop earns a live implementation ONLY if, on the held-out set, deterministic
   promotion-from-recurrence produces reviewer-endorsed rules AND any LLM-surfaced candidates add endorsed value
   over the deterministic pass alone. If the LLM half does not beat deterministic-only, ship deterministic-only
   (the Phase 5C result, rerun for this domain). A null here — promotion adds nothing a human would not have
   promoted anyway — parks the capability, exactly as the neural clean-null did.
3. **Live loop — gated behind a passing retrospective.** Only if step 1 shows signal does the live,
   accumulating promote/extract loop get built. The expensive part is deferred behind the cheap test of the
   part that determines trust.

## Predeclared revisit threshold

This note is reopened — and the step-1 retrospective becomes runnable — only when BOTH hold:

- The decision-history corpus contains enough *independent* decisions carrying blocks that cross-decision
  recurrence is measurable (rule of thumb: on the order of dozens of ADRs/decisions with blocks, with at least
  several repeated patterns across them) — OR an operating-session learnings substrate exists from actually
  *using* the system.
- The maintainer is willing to hand-label a ground-truth promotion set.

Until both hold, the correct action is none: keep building and using; let the substrate accumulate; do not build
a loop that has no fuel and no falsification data.

## Scope note

Two possible scopes — `ai_tools` improving its own rules/ADRs, vs `agent_lib` offering self-improvement as a
*capability* to the agents it builds — hit the same wall. Both need an accumulating-usage substrate; the
capability scope needs it more acutely (per-agent operating histories), and has even less of it today. Neither
is buildable now for the same reason.

## Provenance

The borrowed loop design is from a read (not a run) of a sibling system; see `LESSONS_FROM_OPCOM.md`. The
readiness finding is grounded in the current `ai_tools` ADR corpus (counts above). Behavioral claims about the
sibling system are inferred from source, not validated by execution.
