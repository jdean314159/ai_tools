# ADR-029 — Multi-turn tool-recovery experiment

**Status:** Accepted  
**Date:** 2026-08-29

## Decision

The next observable-process experiment measures whether a model changes course
after a tool interaction makes its first plan untenable. It is a separate
profile, `llm_engines.tool_recovery_campaign`, rather than an extension of the
single-decision profile in ADR-027.

The first campaign covers four failure families:

1. an explicit transient tool error for which one bounded retry is permitted;
2. a tool result that contradicts the model's working assumption;
3. a requested tool reported unavailable when a named alternative exists; and
4. an incomplete result that requires one targeted follow-up lookup.

Tools are not executed. The runner injects fixed synthetic tool results after
the model's first valid call. It then scores only observable subsequent
actions and final answers. Reasoning text is neither retained nor treated as
evidence of recovery.

## Primary outcome

The primary outcome is **correct recovery within the fixed turn and tool-call
budget, without inventing tool success**. A case fails if the model repeats a
disallowed call, claims that a failed tool succeeded, ignores contradictory
tool evidence, exceeds a case budget, or gives the wrong synthetic resolution.
Latency, token use, and call count are secondary descriptive outcomes.

## Headroom and case selection

Case development and evaluation are separate. A development set may adjust
wording and difficulty. Evaluation cases and their scorer are frozen before
matched treatment runs, and cases must not be selected because one treatment
wins them.

Before a live comparison, a pilot using the frozen evaluation cases must show
that the thinking-off baseline is neither zero nor ceiling on the primary
outcome. Otherwise the campaign stops without an intervention claim. Changed
case difficulty requires a new profile version and a new split.

## Predeclared comparison

The first matched comparison is thinking off versus thinking on. It holds the
endpoint, model label, cases, scorer, turn and call budgets, temperature,
requested seed, and repetitions constant. Conditions run sequentially against
an otherwise idle endpoint. Their order is recorded; a fixed-order campaign
supports descriptive differences only.

Improvement requires a higher primary-outcome recovery rate without an
increase in fabricated-success failures. The minimum effect and repetitions
must be frozen in a campaign work order before live runs. Without them, a run
is a pilot and cannot support an improvement claim.

## Durable record and privacy

The version-2 artifact records case IDs, failure families, expected and
observed actions, recovery and fabricated-success status, turn and call
counts, bounded latency/token totals, thinking request, seed request, seed
acceptance, condition order, and frozen-suite identity.

It omits raw prompts, responses, reasoning, injected tool-result values,
endpoint URLs, secrets, and exception messages. Model paths are reduced to a
basename before recording.

## Acceptance observations

- Deterministic fake engines exercise every pass and failure branch.
- The scorer rejects invented success even when the final answer matches.
- Turn and call limits are enforced by the runner.
- Development cases cannot appear in a final evaluation artifact.
- A zero or ceiling thinking-off pilot blocks an improvement campaign.
- Artifacts retain treatment, seed, order, and suite identity while omitting
  raw interaction content.
- No live campaign runs until repetitions and minimum improvement are frozen
  in a separate work order.

## Version-1 withdrawal

The first baseline pilot exposed a scorer defect in version 1. The
contradiction case required the complete natural-language response to equal
`INACTIVE`. The model instead gave a correct sentence stating that the record
was not active and that its actual status was inactive, which the exact-text
check marked wrong. Version 1 therefore measured formatting rather than the
predeclared recovery proposition and is withdrawn.

Version 2 replaces that free-text answer with a typed `report_status` tool
call whose `status` argument must equal `INACTIVE`. This changes the frozen
suite and its digest. The invalid version-1 artifact is retained with an
`invalid-scorer` filename; it is incident evidence, not a baseline result.
