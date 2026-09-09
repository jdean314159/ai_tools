# Ornith model-blind target-transfer pilot result — 2026-09-09

The failure transferred to two previously unused historical targets. Staged v1
and adaptive v2.2 each recalled 0 of 5 valid known-defect opportunities. All
four final reports contained zero accepted findings, so accepted false positives
were also zero and precision is undefined. Adaptive v2.2 did not meet the
preregistered material-improvement rule.

This narrows one uncertainty from the earlier development campaign: 0/3 was
not unique to target `83e1d09`. It does not establish population-level
generalization. Codex selected these targets and wrote their graders, each
target has only one paired seed, and the repository and model are unchanged.

## Objective grader boundary

The model-visible exports excluded the grader sources, defect descriptions,
fix messages, corrected references, and historical project/internal documents.
After all four reports were final, the external reproducers produced these
mechanical results:

| Target | Target result | Corrected reference | Reference result |
| --- | ---: | --- | ---: |
| `23c1549` frozen grader | 3 failed | `49026ea` | 3 passed |
| `23c1549` corrected grader | 2 failed | `49026ea` | 2 passed |
| `7d37920` | 3 failed | `8e2e9e5` | 3 passed |

Semantic review invalidated one frozen `23c1549` row. That target predates the
commit that introduced the Spark configuration and private address; the test
failed because it required the later placeholder, not because the target
contained the prohibited address. The frozen grader is retained unchanged,
and a post-run corrected grader removes only that row. This is a false-fail
scorer case: the test had a clean target/reference split but graded historical
feature absence as a defect.

The five valid behaviors are the tool-policy classification omission,
publication checking that did not fail closed without Git metadata, Engram
path escape, persistent-path permissions, and cross-tenant episode deletion.
The model reports were already final before this correction, so their content
and zero-recall numerator were unaffected.

## Paired result

| Target | Condition | Recall | Coverage | Shell calls | Max concentration | Input tokens | Final findings |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `23c1549` | staged v1 | 0/2 | 7/9 | 30 | 20.0% | 102,316 | 0 |
| `23c1549` | adaptive v2.2 | 0/2 | 2/9 | 45 | 24.4% | 474,829 | 0 |
| `7d37920` | adaptive v2.2 | 0/3 | 3/9 | 32 | 34.4% | 376,571 | 0 |
| `7d37920` | staged v1 | 0/3 | 6/9 | 27 | 11.1% | 113,787 | 0 |
| **v1 summary** |  | **0/5 total** | **6.5/9 median** | **28.5 median** | **15.6% median** | **108,051.5 median** | **0** |
| **v2.2 summary** |  | **0/5 total** | **2.5/9 median** | **38.5 median** | **29.4% median** | **425,700 median** | **0** |

V2.2 used 3.94 times the paired-v1 median input. It covered fewer packages on
both targets, and its `23c1549` run bound the 45-call ceiling. All runs reached
a structured final envelope and reported high remaining uncertainty.

## Preregistered decisions

1. The frozen 0/3-per-target prediction is not evaluable exactly because one
   target denominator was invalid. Corrected recall was 0/2 and 0/3 under both
   conditions, so the substantive zero-recall expectation still held.
2. V1 coverage was at least v2.2 coverage on both targets: 7/9 versus 2/9 and
   6/9 versus 3/9.
3. Neither condition accepted a false positive. With no accepted findings,
   precision is undefined.
4. V2.2 continued to expose evidence-grounding failures. Only 7 of 23 scout
   and verifier evidence records passed exact-quote validation; 16/23 (69.6%)
   were invalid. Conservative downgrades prevented acceptance.
5. V2.2 recalled zero more of the five valid defects than v1. Although the
   frozen rule described six opportunities, its required two-defect gain was
   plainly not met under either denominator.

## What the harness changes did and did not do

V1 allocated effort broadly and cheaply but generated almost no hypotheses.
Its `23c1549` candidate was rejected by the verifier; its `7d37920` run
generated none. It still failed to inspect two or three packages substantively
per target and missed every graded behavior.

V2.2 made all 18 package selections successfully, promoted five hypotheses,
and subjected them to deeper verification. None concerned a graded defect.
Three verifier confirmations or insufficient-evidence paths on `23c1549`
reached two critics, both of which declined acceptance. Both `7d37920`
hypotheses were rejected by their verifiers. Three attempted calls beyond
stage-local budgets were blocked and recorded as protocol violations.

The controller therefore remains useful as a safety and audit boundary: it
bounds execution, exposes invalid evidence, and prevents unsupported final
claims. It does not improve defect selection or recall. On these targets it is
also less efficient and less broad than staged v1. Further prompt or controller
tuning on any of the three used targets would be post-hoc optimization and is
closed.

## Endpoint and validation notes

Both target pairs used the same Ornith model label, llama.cpp build, reported
Q4_0 K/V caches, flash attention, Jinja, and draft-MTP launch settings. The
first pair's sanitized pre/post fingerprints were identical. In the second
pair, the only raw-fingerprint delta was that each idle slot's speculative type
changed from unavailable (`null`) to the explicit `none,draft-mtp` label. Build,
model metadata, context, slot count, health, and speculative enablement were
unchanged. The validator treats null-to-known telemetry as compatible and
still rejects conflicting known values; raw snapshots are retained.

The first validator invocation is retained as invalid because a default path
looked for `tools/tools`. A corrected pre-grader validation and the
pre-semantic-correction validation are also retained. The final validator
confirms all four run identities and hashes, frozen runner and prompt digests,
shell-call ceilings, endpoint material stability, the frozen mechanical grader
outcomes, the corrected 2/2 grader split, and one semantic invalidation.

## Conclusion and next gate

The useful finding is a replicated discontinuity within one model: reliable
performance on self-grading capability and tool-use tasks did not transfer to
autonomous defect discovery, even when external scaffolding made the process
bounded and auditable. The negative recall result now spans three objective
targets and two structured harnesses, but only the two targets here were
model-blind.

No v2.3 or further prompt tuning is selected. A stronger next experiment would
require evaluator-independent target selection, external graders written
before this harness sees the targets, more than one seed per target, and a new
preregistration. Until those inputs exist, this research line stops rather
than consuming more Spark time on the same failure mode.

## Evidence

- [Preregistration](ORNITH-MODEL-BLIND-TRANSFER-PILOT-PREREGISTRATION-2026-09-09.md)
- [Target acquisition and frozen graders](TARGET-ACQUISITION-2026-09-08.md)
- [Campaign evidence](runs/2026-09-09-ornith-model-blind-transfer-pilot/)
- `independent-validation.json`, `independent-grader-results.json`, and
  `independent-adjudication.json` in the campaign directory
- [Maintained validator](tools/validate_model_blind_transfer_pilot.py)

The retained metadata remains experimental and is not the deferred production
`repository-assessment/v1` profile.
