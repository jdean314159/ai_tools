# Post-v2.2 repository-assessment recommendation — 2026-09-08

Status: draft for Claude review. This document does not authorize a new
harness, live model requests, target selection, Phase 2, or reliability-lab
mutation.

## Recommendation

Stop development of the frozen adaptive-v2.2 treatment on target `83e1d09`.
Do not try to recover its performance through prompt wording or another run on
that target. The target, grader, defect list, and multiple failure trajectories
are now known, so further iteration would be tuning to the oracle.

The broader repository-assessment line is not a dead end. A new study is
justified if it changes the mechanisms implicated by the evidence, develops on
a new historical target, and reserves untouched targets for confirmation. The
next design should be a small set of component ablations against staged v1,
not an immediately combined v2.3 treatment.

Running frozen v2.2 unchanged on blinded targets remains permissible under its
preregistered stop rule, but the paired development result makes that a
low-priority replication study rather than the recommended performance path.

## Evidence behind the decision

The valid campaign distinguishes controller correctness from assessment
performance:

- all three v2.2 runs passed every frozen mechanical gate;
- known-defect recall remained 0/3 in all v1 and v2.2 runs;
- median coverage fell from 7/9 under paired staged v1 to 3/9 under v2.2;
- median maximum concentration rose from 20.0% to 28.9%;
- median input rose from 115,521 to 376,075 tokens, or 3.26 times v1;
- every package received the same selected symbol in all three seeds; and
- independent replay rejected 29/35 model-submitted evidence records because
  the cited quotation was not an exact substring of the referenced output.

The evidence gates were useful: neither condition accepted a false positive.
They did not create better hypotheses or defect judgment. The complete result
and limits are in
[the v2.2 assessment](ORNITH-ADAPTIVE-STAGED-V2-2-ASSESSMENT-2026-09-08.md).

## Failure-to-change mapping

| Observed failure | Likely mechanism | Proposed change | Expected effect |
| --- | --- | --- | --- |
| Same package symbol selected in every seed | Deterministic dossier plus unconstrained model choice converged on salient, low-risk symbols | Controller assigns a risk lens and enforces cross-run target diversity | Different behavioral surfaces are actually investigated |
| Median coverage fell to 3/9 | Two scout calls often covered only the selected implementation and one nearby source | Restore a three-call scout sequence: contract/caller, implementation, disconfirmation | Recover breadth while retaining falsification |
| 29/35 evidence records had invalid exact quotes | Verbatim copying is an unreliable model responsibility | Model cites retained evidence IDs; controller carries the referenced output or extracts the canonical span | Grounding becomes mechanically reliable without testing transcription skill |
| Eight unresolved scouts consumed verifier budgets | Promotion rewarded uncertainty instead of observed contradiction | Promote only a defect-shaped observation with an explicit expected/observed delta | Deep budget follows evidence rather than indecision |
| Two verifier `confirmed` records described no demonstrated violation | One categorical label mixed behavior verification with defect confirmation | Separate `behavior_reproduced` from `violation_observed`; only the latter can reach a critic | A correct implementation cannot be called a confirmed defect |
| All 27 scouts needed a forcing request | The model did not treat structured submission as part of its stopping policy | Keep controller-forced completion and measure natural stopping; do not make natural submission a correctness gate | Bounded completion without confusing fluency with task success |

## Proposed component designs

### A. Controller-owned evidence transport

Keep staged-v1 scope allocation and three-call scouts. Replace required copied
quotes with references to retained stage-local evidence IDs. The controller
must place the corresponding bounded output directly into the verifier and
critic record, retaining its digest and command. If a shorter span is needed,
the controller—not the model—extracts and records the canonical span.

This is a direct response to the current exact-substring validator at
`tools/run_adaptive_staged_assessment.py:443-463`. V2.2 correctly rejects bad
copies, but the 82.9% invalid rate shows that exact quotation is measuring a
transcription interface as well as grounding. The durable transcript already
associates a controller-generated evidence ID with each executed result at
`tools/run_adaptive_staged_assessment.py:721-760`.

Prediction to preregister: evidence-reference resolution reaches 100% by
construction and accepted false positives do not increase. No recall increase
should be predicted from this component alone.

### B. Stratified investigation assignment

Keep the model responsible for writing a falsifiable hypothesis, but have the
controller assign a risk lens before selection. Candidate lenses should be
repository-general and derivable without the defect oracle, for example:

- state mutation and partial failure;
- persistence and cache invalidation;
- identity, path, and ownership boundaries;
- concurrency, locking, and atomicity;
- error translation and fallback behavior;
- cross-package adapter contracts; and
- ordering, ranking, and deduplication invariants.

Across repeated seeds on one target, use a preregistered rotation so a package
does not receive the same `(symbol, risk_lens)` pair twice unless its dossier
contains no alternative. Record such exhaustion rather than silently
repeating the target. This changes actual search diversity; merely shuffling
package order did not.

The current selector only requires one dossier-backed symbol and invariant at
`tools/run_adaptive_staged_assessment.py:57-65`, and validation checks
membership rather than risk or cross-run novelty at
`tools/run_adaptive_staged_assessment.py:387-419`. The dossiers already expose
production symbols and test references at
`tools/run_adaptive_staged_assessment.py:305-368`, so the controller can enforce
an assignment without reading oracle data.

Prediction to preregister: cross-seed target diversity increases and median
substantive coverage is no lower than staged v1. Recall remains an empirical
outcome, not an assumed consequence of diversity.

### C. Defect-shaped promotion schema

Replace the overloaded scout/verifier labels with explicit fields:

- `expected_behavior` and its repository basis;
- `observed_behavior` and its evidence IDs;
- `behavior_reproduced: true | false`;
- `violation_observed: true | false`;
- `disconfirmation_attempt` and outcome;
- `impact_demonstrated: true | false`; and
- `reproducer_command_id` or an explicit reason no reproducer is feasible.

Only `violation_observed=true` with valid evidence may be promoted. Only a
verifier with both `violation_observed=true` and
`impact_demonstrated=true` may reach the critic. An unresolved scout is retained
as uncertainty but consumes no verifier allocation.

This replaces the current policy that promotes `supported` and then
`unresolved` records at
`tools/run_adaptive_staged_assessment.py:828-833`. It also prevents a verifier
from using `confirmed` to mean that conforming behavior was confirmed, which
occurred twice in v2.2.

Prediction to preregister: verifier launches decrease, no "confirmed but no
violation" record is representable, and accepted false positives do not
increase. Recall may remain unchanged.

### D. Budget shape

For a later combined treatment, prefer 27 breadth calls and 18 verification
calls within the unchanged 45-call ceiling:

- nine scouts with at most three calls each; and
- at most three promoted hypotheses with at most six verifier calls each.

The scout sequence should explicitly cover (1) contract or caller,
(2) implementation, and (3) execution or strongest feasible disconfirmation.
The current two/nine split is fixed at
`tools/run_adaptive_staged_assessment.py:43-46`. Restoring the three-call scout
budget is motivated by paired-v1 coverage, not by knowledge of which symbols
contain the three graded defects.

## Experimental sequence

### Target gate

An independent evaluator should prepare at least three new historical targets:

1. one development target whose oracle may be disclosed only after the frozen
   development runs; and
2. at least two confirmation targets whose defect identities remain evaluator
   only until every report is final.

Each target needs a frozen source identity and an external grader that fails on
the target and passes on its corrected reference. Target selection must not be
based on compatibility with the proposed risk lenses. Historical fix messages,
grader source, and experiment documents remain masked from the model.

### Development ablations

Use staged v1 as the control and preserve model, endpoint, seeds, masking,
package set, and total shell-call ceiling. Run components independently before
combining them:

1. staged v1 control;
2. v1 plus controller-owned evidence transport and the defect-shaped result
   schema;
3. v1 plus stratified investigation assignment; and
4. a combined treatment only if the relevant component passes its frozen
   mechanism checks and does not regress accepted false positives.

Condition order must be counterbalanced. Freeze predictions and selection
rules before the first live request. Report every seed and preserve invalid
attempts. Do not choose the combined condition after examining only a favorable
seed.

### Outcomes

Primary task outcomes remain external-grader recall and independently
adjudicated accepted false positives. Process measures—coverage, diversity,
evidence resolution, concentration, calls, tokens, and stopping—cannot by
themselves establish improved assessment performance.

A component can be considered mechanically successful without improving
recall. It should advance to a combined treatment only when its intended
mechanism improves and it does not make the primary task outcomes worse. Any
claim that the combined treatment improves judgment requires untouched blinded
confirmation.

## What not to do

- Do not alter and rerun v2.2 on `83e1d09`.
- Do not interpret prompt wording separately from controller, budget, and
  context changes unless the experiment isolates wording.
- Do not promote unresolved hypotheses merely to keep verifiers busy.
- Do not count dossier exposure, a selection request, or a file listing as
  substantive package coverage.
- Do not call zero accepted findings 100% precision; precision is undefined.
- Do not use a stronger model as a substitute for a controlled harness
  comparison. Model choice can be a separate factor after the design is
  mechanically validated.
- Do not export this proposal to the reliability lab as if it were evidence.
  The completed v2.2 result is evidence; this document is a proposed response.

## Questions for Claude review

1. Is stopping the frozen v2.2 line, except for an explicitly motivated blind
   replication, the right reading of the paired negative result?
2. Should evidence transport retain complete bounded tool output, canonical
   controller-extracted spans, or both?
3. Are risk-lens rotation and cross-seed target exclusion sufficiently
   repository-general, or would they introduce a new proxy-gaming surface?
4. Should the evidence-transport and defect-schema changes be one component or
   two separate ablations?
5. What minimum development decision rule justifies paying for the two-target
   blinded confirmation without selecting on noise from three seeds?
6. Should the reliability-lab packet cover only the completed v2.2 result and
   invalid mechanical attempts, leaving this recommendation as maintainer-only
   context?

## Decision boundary

Claude's review may refine this draft, but implementation still requires an
explicitly accepted experiment plan and preregistration. Course placement,
module titles/status, incident-log changes, and evidence-packet schema changes
remain separate maintainer decisions.
