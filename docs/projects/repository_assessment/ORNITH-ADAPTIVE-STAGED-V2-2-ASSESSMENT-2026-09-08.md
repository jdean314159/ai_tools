# Ornith adaptive staged-assessment v2.2 result — 2026-09-08

The v2.2 controller worked as specified, but the treatment did not improve the
repository assessment. All three v2.2 runs passed the seven frozen mechanical
gates and scored 0/3 known-defect recall. Against fresh paired staged-v1 runs,
median substantive coverage fell from 7/9 to 3/9, median maximum package-call
concentration rose from 20.0% to 28.9%, and median input grew from 115,521 to
376,075 tokens. No final report in either condition contained an accepted
finding.

This is a development result on a known target. It does not estimate
generalization or establish that this prompt/controller would behave similarly
on another repository.

## Frozen comparison

The six runs followed the preregistered order and paired seeds. The endpoint
fingerprint was unchanged in all six before/after snapshots. The independent
grader still failed all three behaviors on frozen commit `83e1d09` and passed
all three on corrected commit `61a63fc`.

| Condition | Seed | Recall | Coverage | Shell calls | Max concentration | Input tokens | Final findings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| staged v1 | 17 | 0/3 | 7/9 | 27 | 11.1% | 115,521 | 0 |
| adaptive v2.2 | 17 | 0/3 | 5/9 | 38 | 28.9% | 368,469 | 0 |
| adaptive v2.2 | 31 | 0/3 | 3/9 | 33 | 30.3% | 376,075 | 0 |
| staged v1 | 31 | 0/3 | 8/9 | 30 | 20.0% | 123,613 | 0 |
| staged v1 | 47 | 0/3 | 7/9 | 30 | 20.0% | 105,961 | 0 |
| adaptive v2.2 | 47 | 0/3 | 3/9 | 41 | 26.8% | 478,868 | 0 |
| **v1 median** |  | **0/3** | **7/9** | **30** | **20.0%** | **115,521** | **0** |
| **v2.2 median** |  | **0/3** | **3/9** | **38** | **28.9%** | **376,075** | **0** |

The seed-47 v1 empirical stages completed, but its model synthesizer did not
return the required structure. The deterministic controller fallback was
retained and the run correctly remains `lifecycle: aborted`; this is disclosed
rather than silently treating it as a natural final report.

## Preregistered decisions

1. **Mechanical gates — supported.** All three v2.2 runs passed dossier,
   selection, evidence, budget, verifier, deterministic-report, and grader
   checks under independent replay.
2. **Coverage — contradicted.** The v2.2 median was 3/9, below both the 7/9
   threshold and the paired-v1 median of 7/9.
3. **Concentration — contradicted.** The v2.2 median was 28.9%, above the 25%
   ceiling.
4. **Input below 25% of autonomous baseline — supported.** The v2.2 median of
   376,075 is below 412,197.75. It is a 77.2% reduction from the autonomous
   median, although it is 3.26 times the paired staged-v1 median.
5. **Accepted false positives no worse than v1 — supported.** Both conditions
   accepted zero findings and therefore zero false positives; precision is
   undefined, not 100%.
6. **Recall may remain 0/3 — observed.** Every run in both conditions scored
   0/3. Because the target and prior failures were known during design, this is
   descriptive development evidence only.

## What failed behaviorally

The deterministic dossiers solved orientation but narrowed hypothesis choice.
All 27 package selections succeeded on their first attempt, yet each of the
nine packages received exactly the same selected symbol in all three seeds.
Seed changed package order, not the selected investigation. The result was a
deterministic search tunnel: two calls per package were spent on the same often
low-risk invariant, then promoted unresolved items consumed deeper verifier
budgets. Median empirical coverage fell even though every package received a
selection call.

Evidence discipline exposed a second failure. Independent replay found only 6
of 35 submitted evidence records contained the claimed exact quote in the
referenced same-stage output; 29/35 (82.9%) were invalid. The controller
conservatively downgraded positive scout/verifier claims with invalid evidence.
Of 27 scouts, 16 ended `disproved`, 11 `unresolved`, and none `supported` after
validation. Eight unresolved hypotheses were promoted. Verifiers returned two
`confirmed`, two `rejected`, and four `insufficient_evidence`; both confirmed
records reached critics, and both critics found insufficient evidence. That
gate prevented unsupported acceptance, but it did not supply the missing
defect judgment.

Natural stopping improved only at the verifier layer. None of the 27 scouts
returned its structured result before a forcing request, while five of eight
verifiers did. The controller made completion bounded and auditable; it did not
teach the model what defect to investigate.

## Comparison with the autonomous baseline

V2.2 remains more controlled than the original single-context Ornith baseline:
median coverage was 3/9 rather than 1/9, maximum concentration was 28.9% rather
than 62.2%, and median input was 376,075 rather than 1,648,791 tokens. The
paired comparison is nevertheless the appropriate test of the new treatment,
and there v2.2 regressed on coverage, concentration, calls, and tokens while
recall remained unchanged.

This distinction is the useful reliability result: a controller can be
mechanically correct, reject unsupported claims, and improve over an especially
poor autonomous baseline while still being worse than a simpler structured
control on the process measures it was intended to improve.

## Invalid mechanical-development attempts

Two complete restarts preceded the valid campaign and are retained separately,
not included in behavioral scoring:

- v2 required backend tool-call IDs that llama.cpp's active Jinja template did
  not expose to the model. V2.1 introduced visible stage-local evidence IDs.
- v2.1 discarded two complete negative scout reports because the model repeated
  a controller-owned source label differently. V2.2 retained those repetitions
  for audit while making the frozen selection authoritative.

These are reusable harness lessons: identifiers required by a tool contract
must exist in model-visible context, and invariant bindings already owned by a
controller should not depend on exact model repetition.

## Next gate and reliability-lab use

The known target is exhausted for treatment tuning. Under the frozen stop rule,
v2.2 may either proceed unchanged to a separately preregistered blinded
confirmation or the research line may stop. No independently prepared blinded
target with a hidden oracle is currently retained in this repository, so no
Phase 2 run begins here. A future v2.3 that diversifies target selection would
be a new development study on new targets, not a post-hoc repair of this result.

The campaign is useful material for `llm-failure-lab`, especially as a case in
external checkability, proxy-metric false passes, evidence-reference failure,
and controller/model responsibility boundaries. Export remains closed until
the `ai_tools` evidence has stable committed Git identities, disclosure review
is complete, an independent verifier checks the packet, and the lab's
maintainer authorizes teaching placement. The lab must receive a bounded
evidence packet, not a dependency on this adjacent checkout.

## Evidence

- Frozen preregistrations: [v2](ORNITH-ADAPTIVE-STAGED-V2-PREREGISTRATION-2026-09-07.md),
  [v2.1](ORNITH-ADAPTIVE-STAGED-V2-1-PREREGISTRATION-2026-09-07.md), and
  [v2.2](ORNITH-ADAPTIVE-STAGED-V2-2-PREREGISTRATION-2026-09-07.md).
- Valid campaign: [`runs/2026-09-08-ornith-adaptive-staged-v2-2-development/`](runs/2026-09-08-ornith-adaptive-staged-v2-2-development/).
- Excluded development attempts:
  [`v2`](runs/2026-09-07-ornith-adaptive-staged-v2-development/) and
  [`v2.1`](runs/2026-09-08-ornith-adaptive-staged-v2-1-development/).
- Independent outputs: `independent-validation.json`,
  `independent-adjudication.json`, and `independent-grader-results.json` in the
  valid campaign directory.
- Maintained validator:
  [`tools/validate_adaptive_campaign.py`](tools/validate_adaptive_campaign.py).

The retained metadata is experimental and is not the deferred production
`repository-assessment/v1` profile.

A separate
[post-v2.2 recommendation](ORNITH-POST-V2-2-NEXT-ROUND-RECOMMENDATION-2026-09-08.md)
records the proposed component ablations and questions for Claude review. It is
a draft response to this evidence, not an experiment result or authorization.
